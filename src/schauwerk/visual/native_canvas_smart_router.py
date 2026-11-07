"""Bounded, deterministic obstacle-aware routing for native JSON Canvas edges.

This is a renderer-neutral geometry kernel.  A route reports a conflict instead
of presenting a potentially colliding fallback as collision free.  All geometric
proofs use the actual cubic Bezier convex hull, not a fixed sampling interval.
"""
from __future__ import annotations

import heapq
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

Point = tuple[float, float]
Rect = tuple[float, float, float, float]
PORTS = ("right", "left", "bottom", "top")
NORMALS: dict[str, Point] = {
    "right": (1.0, 0.0), "left": (-1.0, 0.0),
    "bottom": (0.0, 1.0), "top": (0.0, -1.0),
}


@dataclass(frozen=True)
class SmartEdgeRoute:
    path: str
    label_x: float
    label_y: float
    bounds: Rect
    points: tuple[Point, ...]
    from_side: str
    to_side: str
    collision_free: bool
    conflict: str | None = None


def _rect(node: Mapping[str, Any], padding: float) -> Rect:
    x = float(node["x"])
    y = float(node["y"])
    return (x - padding, y - padding, x + float(node["width"]) + padding,
            y + float(node["height"]) + padding)


def _intersection(a: Rect, b: Rect) -> bool:
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def _segment_hits_rect(a: Point, b: Point, r: Rect) -> bool:
    """Liang-Barsky closed-rectangle intersection, conservative at the boundary."""
    min_x, min_y, max_x, max_y = r
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    lo, hi = 0.0, 1.0
    for p, q in ((-dx, a[0] - min_x), (dx, max_x - a[0]),
                 (-dy, a[1] - min_y), (dy, max_y - a[1])):
        if abs(p) < 1e-12:
            if q <= 0.0:
                return False if q < 0.0 else True
            continue
        t = q / p
        if p < 0:
            lo = max(lo, t)
        else:
            hi = min(hi, t)
        if lo > hi:
            return False
    return True


def _clear(a: Point, b: Point, obstacles: Sequence[Rect]) -> bool:
    box = (min(a[0], b[0]), min(a[1], b[1]),
           max(a[0], b[0]), max(a[1], b[1]))
    for r in obstacles:
        if (_intersection(box, r) or
                (r[0] <= a[0] <= r[2] and r[1] <= a[1] <= r[3]) or
                (r[0] <= b[0] <= r[2] and r[1] <= b[1] <= r[3])):
            if _segment_hits_rect(a, b, r):
                return False
    return True


def _side_anchor(node: Mapping[str, Any], side: str, lane: float) -> Point:
    x, y, right, bottom = _rect(node, 0.0)
    cx = (x + right) * 0.5
    cy = (y + bottom) * 0.5
    if side in ("left", "right"):
        cy += max(-(bottom-y)*0.24, min((bottom-y)*0.24, lane))
    else:
        cx += max(-(right-x)*0.24, min((right-x)*0.24, lane))
    if side == "left":
        return (x, cy)
    if side == "right":
        return (right, cy)
    if side == "top":
        return (cx, y)
    return (cx, bottom)


def _add(a: Point, b: Point, scale: float = 1.0) -> Point:
    return (a[0]+scale*b[0], a[1]+scale*b[1])


def _distance(a: Point, b: Point) -> float:
    return math.hypot(a[0]-b[0], a[1]-b[1])


def _round_point(p: Point) -> str:
    return f"{p[0]:.3f} {p[1]:.3f}"


def _dedupe(points: Sequence[Point]) -> tuple[Point, ...]:
    result: list[Point] = []
    for point in points:
        if not result or _distance(result[-1], point) > 0.001:
            result.append(point)
    return tuple(result)


def _curve_hull_clear(
    controls: tuple[Point, Point, Point, Point], obstacles: Sequence[Rect]
) -> bool:
    """De Casteljau recursion with conservative hull/rectangle proof.

    A cubic lies in its four-control-point convex hull.  The bounding rectangle
    of each subdivided hull disjoint from obstacles suffices to certify the
    *entire* continuous curve, not just sampled points.  A limit yields reject.
    """
    stack: list[tuple[tuple[Point, Point, Point, Point], int]] = [(controls, 0)]
    while stack:
        curve, depth = stack.pop()
        xs = [p[0] for p in curve]
        ys = [p[1] for p in curve]
        box = (min(xs), min(ys), max(xs), max(ys))
        near = [r for r in obstacles if _intersection(box, r)]
        if not near:
            continue
        if depth >= 18 or (box[2] - box[0] < 0.0001 and box[3] - box[1] < 0.0001):
            return False
        a,b,c,d=curve
        ab=((a[0]+b[0])/2,(a[1]+b[1])/2)
        bc=((b[0]+c[0])/2,(b[1]+c[1])/2)
        cd=((c[0]+d[0])/2,(c[1]+d[1])/2)
        abc=((ab[0]+bc[0])/2,(ab[1]+bc[1])/2)
        bcd=((bc[0]+cd[0])/2,(bc[1]+cd[1])/2)
        middle=((abc[0]+bcd[0])/2,(abc[1]+bcd[1])/2)
        stack.append(((middle,bcd,cd,d),depth+1))
        stack.append(((a,ab,abc,middle),depth+1))
    return True


def _path_with_safe_fillets(
    points: tuple[Point, ...], obstacles: Sequence[Rect]
) -> str:
    if len(points) < 2:
        return ""
    commands = ["M "+_round_point(points[0])]
    last = points[0]
    for i in range(1,len(points)-1):
        prev, vertex, following = points[i-1:i+2]
        left = _distance(prev, vertex)
        right = _distance(vertex, following)
        if left < 1e-6 or right < 1e-6:
            continue
        di = ((vertex[0]-prev[0])/left,(vertex[1]-prev[1])/left)
        do = ((following[0]-vertex[0])/right,(following[1]-vertex[1])/right)
        cross = di[0]*do[1]-di[1]*do[0]
        if abs(cross) < 0.04:
            commands.append("L "+_round_point(vertex))
            last=vertex
            continue
        radius = min(16.0,left*0.27,right*0.27)
        selected = None
        for _ in range(8):
            entry=_add(vertex,di,-radius)
            leave=_add(vertex,do,radius)
            c1=_add(entry,di,2*radius/3)
            c2=_add(leave,do,-2*radius/3)
            cubic=(entry,c1,c2,leave)
            if _curve_hull_clear(cubic,obstacles):
                selected=cubic
                break
            radius*=0.5
        if selected is not None:
            entry,c1,c2,leave=selected
            if _distance(last,entry)>0.001:
                commands.append("L "+_round_point(entry))
            commands.append("C "+" ".join(_round_point(p) for p in (c1,c2,leave)))
            last=leave
        else:
            commands.append("L "+_round_point(vertex))
            last=vertex
    if _distance(last,points[-1])>0.001:
        commands.append("L "+_round_point(points[-1]))
    return " ".join(commands)


def _label_position(points: tuple[Point,...]) -> Point:
    lengths = [_distance(a,b) for a,b in zip(points,points[1:])]
    total=sum(lengths)
    target=total/2
    for (a,b),length in zip(zip(points,points[1:]),lengths):
        if length >= target:
            portion=target/length if length else 0
            return (a[0]+(b[0]-a[0])*portion,a[1]+(b[1]-a[1])*portion)
        target-=length
    return points[-1]


def _build_graph(
    vertices: Sequence[Point], obstacles: Sequence[Rect]
) -> list[list[tuple[int, float]]]:
    graph: list[list[tuple[int,float]]] = [[] for _ in vertices]
    for i,a in enumerate(vertices):
        for j in range(i+1,len(vertices)):
            b=vertices[j]
            if _clear(a,b,obstacles):
                length=_distance(a,b)
                graph[i].append((j,length))
                graph[j].append((i,length))
    return graph


def _dijkstra(
    graph: Sequence[Sequence[tuple[int, float]]], start: int, end: int
) -> tuple[int, ...] | None:
    dist = [math.inf]*len(graph)
    prev = [-1]*len(graph)
    dist[start]=0.0
    queue = [(0.0,start)]
    while queue:
        cost,i=heapq.heappop(queue)
        if cost>dist[i]+1e-9:
            continue
        if i==end:
            break
        for j,length in graph[i]:
            score=cost+length
            if score<dist[j]-1e-9:
                dist[j]=score
                prev[j]=i
                heapq.heappush(queue,(score,j))
    if not math.isfinite(dist[end]):
        return None
    result=[]
    i=end
    while i != -1:
        result.append(i)
        i=prev[i]
    return tuple(reversed(result))


def route_edge(
    source: Mapping[str, Any], target: Mapping[str, Any],
    nodes: Sequence[Mapping[str, Any]], *,
    from_side: str | None = None, to_side: str | None = None,
    lane: float = 0.0, clearance: float = 12.0,
    max_blockers: int = 24,
) -> SmartEdgeRoute | None:
    """Plan a short obstacle-free path, selecting 4-sided ports when unspecified.

    None means no certified clear path under the budget; callers must expose an
    explicit routing conflict and must NOT identify an old simple curve as clear.
    Self-edges remain owned by the existing renderer-specific loop routine.
    """
    if source["id"] == target["id"]:
        return None
    if from_side is not None and from_side not in PORTS:
        raise ValueError("invalid from_side")
    if to_side is not None and to_side not in PORTS:
        raise ValueError("invalid to_side")
    if not (0<=clearance<=100 and 2<=max_blockers<=128 and math.isfinite(lane)):
        raise ValueError("invalid smart edge router configuration")
    src_id,tgt_id=source["id"],target["id"]
    blocking=[_rect(n,clearance) for n in nodes
              if n["id"] not in {src_id,tgt_id} and n.get("type") != "group"]
    # Source and target rectangles prevent a computed detour from re-entering
    # either endpoint.  The first/last 22px stubs are handled independently.
    source_box=_rect(source,clearance*0.6)
    target_box=_rect(target,clearance*0.6)
    all_boxes=tuple(blocking)+(source_box,target_box)
    source_sides=PORTS if from_side is None else (from_side,)
    target_sides=PORTS if to_side is None else (to_side,)
    stub=max(22.0,clearance+10.0)
    candidates=[]
    for si,ss in enumerate(source_sides):
        start=_side_anchor(source,ss,lane)
        start_exit=_add(start,NORMALS[ss],stub)
        if not _clear(start,start_exit,blocking):
            continue
        for ti,ts in enumerate(target_sides):
            end=_side_anchor(target,ts,lane)
            end_exit=_add(end,NORMALS[ts],stub)
            if not _clear(end_exit,end,blocking):
                continue
            candidates.append((si,ti,ss,ts,start,start_exit,end_exit,end))
    if not candidates:
        return None
    # Candidate blockers: near the bounding corridor; a candidate route is
    # always rechecked against *all* blockers so truncation never fakes success.
    starts=[c[5] for c in candidates]
    ends=[c[6] for c in candidates]
    direct_box=(min(p[0] for p in starts+ends)-80,
                min(p[1] for p in starts+ends)-80,
                max(p[0] for p in starts+ends)+80,
                max(p[1] for p in starts+ends)+80)
    relevant=[r for r in all_boxes if _intersection(direct_box,r)]
    # Endpoint blockers are always needed to prohibit source/target re-entry.
    unique=[]
    for r in relevant + [source_box,target_box]:
        if r not in unique:
            unique.append(r)
    if len(unique) > max_blockers:
        # Keep nearest boxes to the segment between endpoint centers while
        # always retaining both endpoints.  No collision-free claim is made
        # unless the candidate is verified against all_boxes below.
        c0=((source_box[0]+source_box[2])/2,(source_box[1]+source_box[3])/2)
        c1=((target_box[0]+target_box[2])/2,(target_box[1]+target_box[3])/2)
        mid=((c0[0]+c1[0])/2,(c0[1]+c1[1])/2)
        movable=[r for r in unique if r not in (source_box,target_box)]
        movable.sort(
            key=lambda r: (
                math.hypot((r[0] + r[2])/2 - mid[0], (r[1] + r[3])/2 - mid[1]),
                r,
            )
        )
        unique=movable[:max(0,max_blockers-2)]+[source_box,target_box]
    unique.sort()
    vertices=[]
    vertex_index={}
    def add_vertex(p:Point)->int:
        key=(round(p[0],6),round(p[1],6))
        if key not in vertex_index:
            vertex_index[key]=len(vertices)
            vertices.append(p)
        return vertex_index[key]
    for c in candidates:
        add_vertex(c[5])
        add_vertex(c[6])
    for x0,y0,x1,y1 in unique:
        for p in ((x0-0.01,y0-0.01),(x0-0.01,y1+0.01),
                  (x1+0.01,y0-0.01),(x1+0.01,y1+0.01)):
            add_vertex(p)
    graph=_build_graph(vertices,all_boxes)
    best=None
    for si,ti,ss,ts,start,ex,ent,end in candidates:
        route=_dijkstra(graph,add_vertex(ex),add_vertex(ent))
        if route is None:
            continue
        poly=_dedupe((start,ex,*[vertices[i] for i in route],ent,end))
        if not all(_clear(a,b,blocking) for a,b in zip(poly,poly[1:])):
            continue
        # Exclude only the stub of its own endpoint from total checks.
        if not all(_clear(a,b,all_boxes) for a,b in zip(poly[1:-2],poly[2:-1])):
            continue
        length=sum(_distance(a,b) for a,b in zip(poly,poly[1:]))
        turn_count=sum(abs((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]))>1e-3
                       for a,b,c in zip(poly,poly[1:],poly[2:]))
        score=length+turn_count*3.0
        if best is None or (score,si,ti)<best[0]:
            best=((score,si,ti),ss,ts,poly)
    if best is None:
        return None
    _,ss,ts,poly=best
    path=_path_with_safe_fillets(poly,all_boxes)
    label=_label_position(poly)
    xs=[p[0] for p in poly]
    ys=[p[1] for p in poly]
    return SmartEdgeRoute(path=path,label_x=label[0],label_y=label[1],
                          bounds=(min(xs),min(ys),max(xs),max(ys)),
                          points=poly,from_side=ss,to_side=ts,collision_free=True)
