"""Deterministic, conservative smart-route geometry regression fixtures."""
import pytest

from schauwerk.visual.native_canvas_smart_router import (
    _curve_hull_clear,
    route_edge,
)


def node(id, x, y, w=100, h=80, type="text"):
    return {"id": id, "x": x, "y": y, "width": w, "height": h, "type": type}


def _sample_path(path):
    """Independent evaluation of emitted M/L/C commands for geometric readback."""
    parts = path.split()
    i = 0
    pos = None
    samples = []
    while i < len(parts):
        cmd = parts[i]
        i += 1
        if cmd in ("M", "L"):
            point = tuple(map(float, parts[i:i+2]))
            i += 2
            if pos is not None:
                samples.extend(
                    (pos[0] + (point[0] - pos[0])*t/200,
                     pos[1] + (point[1] - pos[1])*t/200)
                    for t in range(201)
                )
            pos = point
        elif cmd == "C":
            coords = list(map(float, parts[i:i+6]))
            i += 6
            c1, c2, end = (coords[:2], coords[2:4], coords[4:6])
            assert pos is not None
            for t in range(201):
                k=t/200
                x=((1-k)**3*pos[0]+3*(1-k)**2*k*c1[0]
                   +3*(1-k)*k*k*c2[0]+k**3*end[0])
                y=((1-k)**3*pos[1]+3*(1-k)**2*k*c1[1]
                   +3*(1-k)*k*k*c2[1]+k**3*end[1])
                samples.append((x,y))
            pos = tuple(end)
        else:
            raise AssertionError("unexpected path command " + cmd)
    return samples


def test_direct_route_prefers_short_horizontal_port_pair():
    a,b = node("a",0,0), node("b",400,0)
    result = route_edge(a,b,[a,b])
    assert result is not None and result.collision_free
    assert result.from_side == "right" and result.to_side == "left"
    assert result.label_x == pytest.approx(250)
    assert result.path.startswith("M 100.000 40.000")


def test_vertical_layout_selects_top_bottom_ports_automatically():
    a,b = node("a",0,200),node("b",0,-100)
    route = route_edge(a,b,[a,b])
    assert route is not None
    assert (route.from_side,route.to_side) == ("top","bottom")


def test_blocking_node_is_detoured_by_complete_bezier_curve():
    a,b = node("a",0,0),node("b",400,0)
    blocker=node("blocker",200,0)
    result=route_edge(a,b,[a,b,blocker])
    assert result is not None and result.collision_free
    assert "C " in result.path
    # Dense sampling is only an additional regression oracle. The algorithm's
    # own collision proof is conservative, using recursive cubic hull bounds.
    for x,y in _sample_path(result.path):
        assert not (188.0 < x < 312.0 and -12.0 < y < 92.0)
    assert result.label_y < 0 or result.label_y > 80


def test_manual_ports_take_precedence_even_if_longer():
    a,b=node("a",0,0),node("b",400,0)
    result=route_edge(a,b,[a,b],from_side="top",to_side="bottom")
    assert result is not None
    assert result.from_side == "top" and result.to_side == "bottom"
    assert result.points[0] == (50.0,0.0)
    assert result.points[-1] == (450.0,80.0)


def test_groups_are_visual_surfaces_not_solid_obstacles():
    a,b=node("a",0,0),node("b",400,0)
    group=node("group",120,-100,200,300,"group")
    result=route_edge(a,b,[a,b,group])
    assert result is not None
    assert result.from_side == "right"
    assert result.label_y==pytest.approx(40.0)


def test_self_edges_delegate_to_existing_loop_router():
    a=node("a",0,0)
    assert route_edge(a,a,[a]) is None


def test_invalid_ports_and_budget_fail_explicitly():
    a,b=node("a",0,0),node("b",400,0)
    with pytest.raises(ValueError):
        route_edge(a,b,[a,b],from_side="diagonal")
    with pytest.raises(ValueError):
        route_edge(a,b,[a,b],max_blockers=1)


def test_overlap_reports_conflict_not_silent_success():
    a,b=node("a",0,0),node("b",0,0)
    # Even different IDs can have geometrically indistinguishable full boxes.
    b["id"]="b"
    result=route_edge(a,b,[a,b,node("surround",-200,-200,500,500)])
    assert result is None


def test_cubic_hull_collision_proof_fails_closed_at_uncertain_boundary():
    controls=((0.,0.),(10.,10.),(20.,-10.),(30.,0.))
    assert not _curve_hull_clear(controls,[(14.,-1.,16.,1.)])
    assert _curve_hull_clear(controls,[(100.,100.,120.,120.)])


def test_route_is_deterministic_under_permuted_obstacle_order():
    a,b=node("a",0,0),node("b",500,0)
    blocks=[node("c",160,0),node("d",320,0)]
    first=route_edge(a,b,[a,b,*blocks])
    second=route_edge(a,b,[*blocks[::-1],b,a])
    assert first is not None and second is not None
    assert first.path==second.path


def test_fixed_ports_cannot_cross_the_other_endpoint_before_the_port():
    a = node("a", 0, 0)
    b = node("b", 10, 0)
    assert route_edge(a, b, [a, b], from_side="right", to_side="right") is None
    assert route_edge(a, b, [a, b], from_side="left", to_side="left") is None


def test_reciprocal_smart_rails_remain_separate_and_selectable():
    """Opposite edge hit corridors must not coincide over an obstacle.

    Production Chrome RED: with only per-port lane offsets the entire
    forward hit path was intercepted by the reverse edge (0/51 hits).
    """
    a = node("a", 40, 80, 220, 120)
    b = node("b", 590, 80, 220, 120)
    blocker = node("middle", 310, 50, 200, 200)
    nodes = [a, b, blocker]
    outbound = route_edge(a, b, nodes, lane=-9.0, max_lane=9.0)
    inbound = route_edge(b, a, nodes, lane=9.0, max_lane=9.0)
    assert outbound is not None and inbound is not None
    assert outbound.collision_free and inbound.collision_free
    assert (outbound.from_side, outbound.to_side) == ("right", "left")
    assert (inbound.from_side, inbound.to_side) == ("left", "right")
    # A 24-unit rail gap is wider than the browser's transparent edge
    # hit-stroke corridor; do not just shift the endpoint anchors.
    assert abs(outbound.label_y - inbound.label_y) >= 22.0


def test_reciprocal_rails_stay_separate_below_and_beside_blockers():
    """Rail reservations work on either transverse axis and detour side."""
    a, b = node("a", 40, 80, 220, 120), node("b", 590, 80, 220, 120)
    obstacle = node("middle", 310, 50, 200, 200)
    roof = node("roof", 300, -200, 220, 240)
    bottom_nodes = [a, b, obstacle, roof]
    forward = route_edge(a, b, bottom_nodes, lane=-9, max_lane=9)
    reverse = route_edge(b, a, bottom_nodes, lane=9, max_lane=9)
    assert forward is not None and reverse is not None
    assert forward.label_y > 250 and reverse.label_y > 250
    assert reverse.label_y - forward.label_y >= 22.0

    upper = node("upper", 80, 40, 120, 220)
    lower = node("lower", 80, 590, 120, 220)
    middle = node("middle", 50, 310, 200, 200)
    vertical_nodes = [upper, lower, middle]
    down = route_edge(upper, lower, vertical_nodes, lane=-9, max_lane=9)
    up = route_edge(lower, upper, vertical_nodes, lane=9, max_lane=9)
    assert down is not None and up is not None
    assert up.label_x - down.label_x >= 22.0


def test_four_parallel_obstacle_detours_keep_distinct_rails():
    a, b = node("a", 40, 80, 220, 120), node("b", 590, 80, 220, 120)
    blocker = node("middle", 310, 50, 200, 200)
    nodes = [a, b, blocker]
    y_positions = []
    for index, lane in enumerate((-27.0, -9.0, 9.0, 27.0)):
        source, target = (a, b) if index % 2 == 0 else (b, a)
        route = route_edge(source, target, nodes, lane=lane, max_lane=27.0)
        assert route is not None and route.collision_free
        y_positions.append(route.label_y)
    assert all(
        high - low >= 22.0
        for low, high in zip(sorted(y_positions), sorted(y_positions)[1:])
    )


def test_fixed_port_stub_uses_physical_clearance_not_transverse_rail():
    """A cosmetic sibling rail must not block a valid manually chosen port."""
    a = node("a", 0, 0)
    b = node("b", 400, 0)
    near = node("near", 110, 65)
    # P2 Codex fixture: old source has a valid y=31 fixed-right-to-left
    # connection; the new 24px virtual rail shadow made it return None.
    route = route_edge(
        a, b, [a, b, near], lane=-9.0, max_lane=9.0,
        from_side="right", to_side="left",
    )
    assert route is not None and route.collision_free
    assert (route.from_side, route.to_side) == ("right", "left")
    assert route.points[0] == (100.0, 31.0)
    assert route.points[-1] == (400.0, 31.0)

    # Actual node clearance remains binding even with an explicit port.
    intruder = node("intruder", 110, 20)
    assert route_edge(
        a, b, [a, b, intruder], lane=-9.0, max_lane=9.0,
        from_side="right", to_side="left",
    ) is None


def test_virtual_rail_failure_retries_physically_clear_narrow_passage():
    """A reserved hit-rail may not close the only physically traversable exit.

    Codex P2 fixture: both manually chosen stubs remain clear, but the
    virtual blockers intersect and seal an otherwise unobstructed corridor.
    """
    a = node("a", 0, 0)
    b = node("b", 600, 0)
    blockers = [
        node("west", -200, -300, 50, 600),
        node("roof", -200, -300, 600, 50),
        node("floor", -200, 200, 600, 50),
        node("east-top", 300, -300, 50, 315),
        node("east-bottom", 300, 60, 50, 190),
    ]
    route = route_edge(
        a, b, [a, b, *blockers],
        from_side="right", to_side="left",
        lane=-9.0, max_lane=9.0,
    )
    assert route is not None and route.collision_free
    assert (route.from_side, route.to_side) == ("right", "left")
    assert route.points[0] == (100.0, 31.0)
    assert route.points[-1] == (600.0, 31.0)
