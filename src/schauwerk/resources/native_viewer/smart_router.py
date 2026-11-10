"""Browser-side deterministic smart router. No service, no generated imagery."""
# ruff: noqa: E501

SMART_ROUTER_JS = r"""// Bounded Canvas router. Mirror of native_canvas_smart_router.py.
// Source input is SVG-coordinate node rectangles; no DOM or document mutation.
const PORTS = ["right", "left", "bottom", "top"];
const NORMALS = { right: [1, 0], left: [-1, 0], bottom: [0, 1], top: [0, -1] };
const distance = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
const add = (a, b, scale = 1) => [a[0] + scale * b[0], a[1] + scale * b[1]];
const formatPoint = (p) => p[0].toFixed(3) + " " + p[1].toFixed(3);
const rect = (n, p = 0) => [
  Number(n.x) - p, Number(n.y) - p,
  Number(n.x) + Number(n.width) + p,
  Number(n.y) + Number(n.height) + p,
];
const overlaps = (a, b) =>
  a[0] < b[2] && a[2] > b[0] && a[1] < b[3] && a[3] > b[1];
function segmentHits(a, b, r) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  let lo = 0, hi = 1;
  for (const [p, q] of [
    [-dx, a[0] - r[0]], [dx, r[2] - a[0]],
    [-dy, a[1] - r[1]], [dy, r[3] - a[1]],
  ]) {
    if (Math.abs(p) < 1e-12) {
      if (q <= 0) return q < 0 ? false : true;
      continue;
    }
    const t = q / p;
    if (p < 0) lo = Math.max(lo, t);
    else hi = Math.min(hi, t);
    if (lo > hi) return false;
  }
  return true;
}
function clear(a, b, obstacles) {
  const box = [
    Math.min(a[0], b[0]), Math.min(a[1], b[1]),
    Math.max(a[0], b[0]), Math.max(a[1], b[1]),
  ];
  for (const r of obstacles) {
    const inside = (p) =>
      r[0] <= p[0] && p[0] <= r[2] && r[1] <= p[1] && p[1] <= r[3];
    if ((overlaps(box, r) || inside(a) || inside(b)) && segmentHits(a, b, r))
      return false;
  }
  return true;
}
function sideAnchor(node, side, lane, maxLane = null) {
  const [x, y, right, bottom] = rect(node);
  let cx = (x + right) / 2, cy = (y + bottom) / 2;
  const span = side === "left" || side === "right" ? bottom-y : right-x;
  const limit = span * (maxLane === null ? 0.24 : 0.38);
  const offset = Math.max(-limit, Math.min(limit,
    lane * Math.min(1, limit / Math.max(1, maxLane ?? 0))));
  if (side === "left" || side === "right") cy += offset;
  else cx += offset;
  if (side === "left") return [x, cy];
  if (side === "right") return [right, cy];
  if (side === "top") return [cx, y];
  return [cx, bottom];
}
function hullClear(controls, obstacles) {
  const stack = [[controls, 0]];
  while (stack.length) {
    const [curve, depth] = stack.pop();
    const xs = curve.map(p => p[0]), ys = curve.map(p => p[1]);
    const box = [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
    if (!obstacles.some(r => overlaps(box, r))) continue;
    if (depth >= 18 || (box[2] - box[0] < 0.0001 && box[3] - box[1] < 0.0001))
      return false;
    const [a, b, c, d] = curve;
    const mid = (p, q) => [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2];
    const ab = mid(a, b), bc = mid(b, c), cd = mid(c, d);
    const abc = mid(ab, bc), bcd = mid(bc, cd), middle = mid(abc, bcd);
    stack.push([[middle, bcd, cd, d], depth + 1]);
    stack.push([[a, ab, abc, middle], depth + 1]);
  }
  return true;
}
function filletPath(points, boxes) {
  if (points.length < 2) return "";
  const commands = ["M " + formatPoint(points[0])];
  let last = points[0];
  for (let i = 1; i < points.length - 1; i++) {
    const prev = points[i - 1], vertex = points[i], following = points[i + 1];
    const left = distance(prev, vertex), right = distance(vertex, following);
    if (left < 1e-6 || right < 1e-6) continue;
    const di = [(vertex[0] - prev[0]) / left, (vertex[1] - prev[1]) / left];
    const dirOut = [(following[0] - vertex[0]) / right, (following[1] - vertex[1]) / right];
    const cross = di[0] * dirOut[1] - di[1] * dirOut[0];
    if (Math.abs(cross) < 0.04) {
      commands.push("L " + formatPoint(vertex));
      last = vertex;
      continue;
    }
    let radius = Math.min(16, left * 0.27, right * 0.27);
    let selected = null;
    for (let k = 0; k < 8; k++) {
      const entry = add(vertex, di, -radius);
      const leave = add(vertex, dirOut, radius);
      const c1 = add(entry, di, 2 * radius / 3);
      const c2 = add(leave, dirOut, -2 * radius / 3);
      const cubic = [entry, c1, c2, leave];
      if (hullClear(cubic, boxes)) { selected = cubic; break; }
      radius *= 0.5;
    }
    if (selected) {
      const [entry, c1, c2, leave] = selected;
      if (distance(last, entry) > 0.001) commands.push("L " + formatPoint(entry));
      commands.push("C " + [c1, c2, leave].map(formatPoint).join(" "));
      last = leave;
    } else {
      commands.push("L " + formatPoint(vertex));
      last = vertex;
    }
  }
  if (distance(last, points[points.length - 1]) > 0.001)
    commands.push("L " + formatPoint(points[points.length - 1]));
  return commands.join(" ");
}
function labelPosition(points) {
  const lengths = [];
  let total = 0;
  for (let i = 1; i < points.length; i++) {
    const len = distance(points[i - 1], points[i]);
    lengths.push(len);
    total += len;
  }
  let target = total / 2;
  for (let i = 0; i < lengths.length; i++) {
    const len = lengths[i], a = points[i], b = points[i + 1];
    if (len >= target) {
      const part = len ? target / len : 0;
      return [a[0] + (b[0] - a[0]) * part, a[1] + (b[1] - a[1]) * part];
    }
    target -= len;
  }
  return points[points.length - 1];
}
function dijkstra(graph, from, to) {
  const dist = new Array(graph.length).fill(Infinity);
  const previous = new Array(graph.length).fill(-1);
  const done = new Set(), queue = [[0, from]];
  dist[from] = 0;
  while (queue.length) {
    queue.sort((a, b) => b[0] - a[0] || b[1] - a[1]);
    const [cost, i] = queue.pop();
    if (done.has(i) || cost > dist[i] + 1e-9) continue;
    done.add(i);
    if (i === to) break;
    for (const [j, length] of graph[i]) {
      const score = cost + length;
      if (score < dist[j] - 1e-9) {
        dist[j] = score;
        previous[j] = i;
        queue.push([score, j]);
      }
    }
  }
  if (!Number.isFinite(dist[to])) return null;
  const result = [];
  for (let i = to; i !== -1; i = previous[i]) result.push(i);
  return result.reverse();
}
const lexRect = (a, b) => {
  for (let i = 0; i < 4; i++) if (a[i] !== b[i]) return a[i] - b[i];
  return 0;
};
const equalRect = (a, b) => a.every((x, i) => x === b[i]);

export function smartEdgeGeometry(source, target, nodes, options = {}) {
  if (source.id === target.id) return null;
  const fromSide = options.fromSide ?? null, toSide = options.toSide ?? null;
  if (fromSide !== null && !PORTS.includes(fromSide)) return null;
  if (toSide !== null && !PORTS.includes(toSide)) return null;
  const lane = Number(options.lane ?? 0);
  const maxLane = options.maxLane ?? null;
  const clearance = 12, maxBlockers = 24;
  if (!Number.isFinite(lane) ||
      (maxLane !== null && (!Number.isFinite(maxLane) || maxLane < 0)))
    return null;
  // Mirror the Python transverse rail reservation. A shared obstacle
  // corridor must not hide earlier reciprocal/parallel edge hit paths.
  // Along-route clearance remains fixed to preserve the endpoint stubs.
  const railStep = maxLane !== null && maxLane > 0
    ? Math.min(4 / 3, 96 / Math.max(18, 2 * maxLane)) : 0;
  const railBefore = Math.min(96, Math.max(0, (maxLane ?? 0) - lane) * railStep);
  const railAfter = Math.min(96, Math.max(0, (maxLane ?? 0) + lane) * railStep);
  const horizontal = Math.abs(
    source.x + source.width / 2 - target.x - target.width / 2
  ) >= Math.abs(
    source.y + source.height / 2 - target.y - target.height / 2
  );
  const useRailReservation = options._useRailReservation !== false;
  const blocking = nodes.filter(n =>
    n.id !== source.id && n.id !== target.id && n.type !== "group"
  ).map(n => {
    const physical = rect(n, clearance);
    if (!useRailReservation) return physical;
    const [x0, y0, x1, y1] = physical;
    return horizontal
      ? [x0, y0 - railBefore, x1, y1 + railAfter]
      : [x0 - railBefore, y0, x1 + railAfter, y1];
  });
  const retryPhysical = () =>
    useRailReservation && (railBefore > 0 || railAfter > 0)
      ? smartEdgeGeometry(source, target, nodes,
          {...options, _useRailReservation: false})
      : null;
  const sourceBox = rect(source, clearance * 0.6);
  const targetBox = rect(target, clearance * 0.6);
  const allBoxes = [...blocking, sourceBox, targetBox];
  const sourceSides = fromSide === null ? PORTS : [fromSide];
  const targetSides = toSide === null ? PORTS : [toSide];
  const stub = Math.max(22, clearance + 10), candidates = [];
  sourceSides.forEach((ss, si) => {
    const start = sideAnchor(source, ss, lane, maxLane);
    const ex = add(start, NORMALS[ss], stub);
    if (!clear(start, ex, [...blocking, targetBox])) return;
    targetSides.forEach((ts, ti) => {
      const end = sideAnchor(target, ts, lane, maxLane);
      const ent = add(end, NORMALS[ts], stub);
      if (clear(ent, end, [...blocking, sourceBox]))
        candidates.push([si, ti, ss, ts, start, ex, ent, end]);
    });
  });
  if (!candidates.length) return retryPhysical();
  const corridor = [...candidates.map(c => c[5]), ...candidates.map(c => c[6])];
  const xs = corridor.map(p => p[0]), ys = corridor.map(p => p[1]);
  const direct = [Math.min(...xs) - 80, Math.min(...ys) - 80,
                  Math.max(...xs) + 80, Math.max(...ys) + 80];
  const relevant = allBoxes.filter(r => overlaps(direct, r));
  let unique = [];
  for (const r of [...relevant, sourceBox, targetBox]) {
    if (!unique.some(x => equalRect(x, r))) unique.push(r);
  }
  if (unique.length > maxBlockers) {
    const c0 = [(sourceBox[0] + sourceBox[2]) / 2, (sourceBox[1] + sourceBox[3]) / 2];
    const c1 = [(targetBox[0] + targetBox[2]) / 2, (targetBox[1] + targetBox[3]) / 2];
    const mid = [(c0[0] + c1[0]) / 2, (c0[1] + c1[1]) / 2];
    const movable = unique.filter(r => !equalRect(r, sourceBox) && !equalRect(r, targetBox));
    movable.sort((a, b) => {
      const da = Math.hypot((a[0] + a[2]) / 2 - mid[0], (a[1] + a[3]) / 2 - mid[1]);
      const db = Math.hypot((b[0] + b[2]) / 2 - mid[0], (b[1] + b[3]) / 2 - mid[1]);
      return da - db || lexRect(a, b);
    });
    unique = [...movable.slice(0, Math.max(0, maxBlockers - 2)), sourceBox, targetBox];
  }
  unique.sort(lexRect);
  const vertices = [], indices = new Map();
  function vertexIndex(p) {
    const key = p[0].toFixed(6) + ":" + p[1].toFixed(6);
    if (!indices.has(key)) { indices.set(key, vertices.length); vertices.push(p); }
    return indices.get(key);
  }
  for (const c of candidates) { vertexIndex(c[5]); vertexIndex(c[6]); }
  for (const [x0, y0, x1, y1] of unique) {
    for (const p of [
      [x0 - 0.01, y0 - 0.01], [x0 - 0.01, y1 + 0.01],
      [x1 + 0.01, y0 - 0.01], [x1 + 0.01, y1 + 0.01],
    ]) vertexIndex(p);
  }
  const buildGraph = obstacles => {
    const graph = vertices.map(() => []);
    for (let i = 0; i < vertices.length; i++) {
      for (let j = i + 1; j < vertices.length; j++) {
        if (clear(vertices[i], vertices[j], obstacles)) {
          const length = distance(vertices[i], vertices[j]);
          graph[i].push([j, length]);
          graph[j].push([i, length]);
        }
      }
    }
    return graph;
  };
  const bestRoute = graph => {
    let best = null;
    for (const [si, ti, ss, ts, start, ex, ent, end] of candidates) {
      const route = dijkstra(graph, vertexIndex(ex), vertexIndex(ent));
      if (route === null) continue;
      const poly = [];
      for (const p of [start, ex, ...route.map(i => vertices[i]), ent, end]) {
        if (!poly.length || distance(poly[poly.length - 1], p) > 0.001) poly.push(p);
      }
      if (poly.slice(1).some((p, i) => !clear(poly[i], p, blocking))) continue;
      let blocked = false;
      for (let i = 1; i < poly.length - 2; i++) {
        if (!clear(poly[i], poly[i + 1], allBoxes)) { blocked = true; break; }
      }
      if (blocked) continue;
      let length = 0, turns = 0;
      for (let i = 1; i < poly.length; i++) length += distance(poly[i - 1], poly[i]);
      for (let i = 1; i < poly.length - 1; i++) {
        const a = poly[i - 1], b = poly[i], c = poly[i + 1];
        const cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]);
        if (Math.abs(cross) > 1e-3) turns++;
      }
      const score = length + turns * 3;
      if (!best || score < best.score ||
          (score === best.score && (si < best.si || (si === best.si && ti < best.ti))))
        best = { score, si, ti, ss, ts, poly };
    }
    return best;
  };
  // Local candidates are collision-certified against every node; retry
  // the full graph only when the truncated search cannot find a safe path.
  let best = bestRoute(buildGraph(unique));
  if (!best && unique.length !== allBoxes.length)
    best = bestRoute(buildGraph(allBoxes));
  if (!best) return retryPhysical();
  const { poly, ss, ts } = best;
  const label = labelPosition(poly);
  return {
    path: filletPath(poly, allBoxes),
    labelX: label[0], labelY: label[1],
    fromSide: ss, toSide: ts, points: poly, collisionFree: true,
  };
}

"""
