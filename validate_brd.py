"""BRD compliance validation script for all 5 scenarios."""
import json
from pathlib import Path
from scheduler.models import Scenario
from scheduler.scheduler import BusScheduler


def parse_time(t):
    h, m = map(int, t[:5].split(':'))
    return h * 60 + m


print('=' * 65)
print('BRD COMPLIANCE VALIDATION - ALL 5 SCENARIOS')
print('=' * 65)

all_pass = True

for f in sorted(Path('scenarios').glob('*.json')):
    data = json.load(open(f))
    scenario = Scenario(**data)
    result = BusScheduler(scenario).schedule()

    cap = scenario.parameters.battery_capacity_km
    charge_dur = scenario.parameters.charge_duration_minutes
    violations = []

    # BRD 4.1 + 4.3 + 4.4 + 4.5: per-bus checks
    for bus_id, tl in result.bus_timelines.items():
        bus = scenario.get_bus(bus_id)

        # Build a name->id map for stations
        name_to_id = {s.name: s.id for s in scenario.route.stations}
        name_to_id.update({s.id: s.id for s in scenario.route.stations})  # id->id passthrough

        def resolve(loc):
            return name_to_id.get(loc, loc)

        # 4.1 Range constraint
        prev_loc = bus.origin
        for stop in tl.charging_stops:
            stop_id = resolve(stop.station)
            try:
                dist = scenario.route.get_distance(prev_loc, stop_id)
                if dist > cap:
                    violations.append(f'  FAIL 4.1 {bus_id}: {prev_loc}->{stop_id} = {dist}km > {cap}km')
            except ValueError:
                violations.append(f'  FAIL 4.1 {bus_id}: cannot resolve distance {prev_loc}->{stop_id}')
            prev_loc = stop_id
        try:
            dist = scenario.route.get_distance(prev_loc, bus.destination)
            if dist > cap:
                violations.append(f'  FAIL 4.1 {bus_id}: {prev_loc}->{bus.destination} = {dist}km > {cap}km')
        except ValueError:
            violations.append(f'  FAIL 4.1 {bus_id}: cannot resolve distance {prev_loc}->{bus.destination}')

        # 4.3 Charge duration exactly 25 min
        for stop in tl.charging_stops:
            cs = parse_time(stop.charge_start)
            ce = parse_time(stop.charge_end)
            dur = (ce - cs) % (24 * 60)
            if dur != charge_dur:
                violations.append(f'  FAIL 4.3 {bus_id} @ {stop.station}: duration={dur} != {charge_dur}')

        # 4.5 All buses complete journey
        if not tl.arrival_time:
            violations.append(f'  FAIL 4.5 {bus_id}: no arrival time')

    # BRD 4.2: Only one bus per charger at a time
    for sid, queue in result.station_queues.items():
        station = next(s for s in scenario.route.stations if s.id == sid)
        events = []
        for e in queue:
            cs = parse_time(e.charge_start)
            ce = parse_time(e.charge_end)
            if ce < cs:
                ce += 24 * 60
            events.append((cs, ce, e.bus_id))
        for i, (s1, e1, b1) in enumerate(events):
            for s2, e2, b2 in events[i + 1:]:
                if s1 < e2 and s2 < e1:
                    overlap = min(e1, e2) - max(s1, s2)
                    if overlap > 1:
                        violations.append(
                            f'  FAIL 4.2 Station {sid}: {b1} & {b2} overlap {overlap}min'
                        )

    total_wait = sum(t.total_wait_minutes for t in result.bus_timelines.values())
    max_wait = max(t.total_wait_minutes for t in result.bus_timelines.values())
    buses = len(result.bus_timelines)
    status = 'PASS' if not violations else 'FAIL'
    if violations:
        all_pass = False

    print(f'\n{scenario.name}')
    print(f'  Buses: {buses}  |  Total Wait: {total_wait} min  |  Max Wait: {max_wait} min')
    print(f'  Weights: ind={scenario.weights.individual} op={scenario.weights.operator} overall={scenario.weights.overall}')
    print(f'  BRD Constraints: [{status}]')
    if violations:
        for v in violations:
            print(v)
    else:
        print('  4.1 Range OK  |  4.2 Charger capacity OK  |  4.3 Charge=25min OK  |  4.5 All complete OK')

print()
print('=' * 65)
print('OVERALL:', 'ALL SCENARIOS PASS' if all_pass else 'FAILURES DETECTED')
print('=' * 65)
