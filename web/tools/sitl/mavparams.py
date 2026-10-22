"""Small MAVLink parameter client used for the experiments (QGC-like behaviour).

  save <out.params> [NAME=VALUE ...]  set the given params, then download all and write a QGC .params file
  load <in.params> <report.tsv>       QGC-style load: send each file entry that differs, record the outcome,
                                      then read every entry back
"""
import struct, sys, time
from pymavlink import mavutil

INT_TYPES = {1, 2, 3, 4, 5, 6}  # MAV_PARAM_TYPE_*INT8..INT32

def connect():
    m = mavutil.mavlink_connection("udpin:0.0.0.0:14550")
    hb = m.wait_heartbeat(timeout=60)
    assert hb is not None, "no heartbeat"
    # wait for the autopilot's own heartbeat (component 1)
    while hb.get_srcComponent() != 1:
        hb = m.wait_heartbeat(timeout=10)
    return m

def decode(msg):
    v = msg.param_value
    if msg.param_type in INT_TYPES:
        return struct.unpack("<i", struct.pack("<f", v))[0]
    return v

def encode(value, ptype):
    if ptype in INT_TYPES:
        return struct.unpack("<f", struct.pack("<i", int(value)))[0]
    return float(value)

def fetch_all(m):
    # the parameter count can grow while modules start, so repeat until two downloads agree
    prev = None
    for _ in range(5):
        cur = fetch_once(m)
        if prev is not None and set(cur) == set(prev):
            return cur
        prev = cur
        time.sleep(2)
    raise AssertionError("parameter set did not settle")

def fetch_once(m):
    # the first request can go unanswered while the vehicle is still starting; ask again
    for _ in range(10):
        params = fetch_list(m)
        if params is not None:
            return params
    raise AssertionError("no PARAM_VALUE received")

def fetch_list(m):
    m.mav.param_request_list_send(1, 1)
    params, count, last = {}, None, time.time()
    while time.time() - last < 3:
        msg = m.recv_match(type="PARAM_VALUE", blocking=True, timeout=0.5)
        if msg is None:
            continue
        last = time.time()
        count = msg.param_count
        params[msg.param_id] = (decode(msg), msg.param_type, msg.param_index)
        if len(params) >= count:
            break
    if count is None:
        return None
    have = {p[2] for p in params.values()}
    for idx in [i for i in range(count) if i not in have]:
        m.mav.param_request_read_send(1, 1, b"", idx)
        msg = m.recv_match(type="PARAM_VALUE", blocking=True, timeout=2)
        if msg:
            params[msg.param_id] = (decode(msg), msg.param_type, msg.param_index)
    assert len(params) >= count, f"got {len(params)} of {count}"
    return params

def read_one(m, name, timeout=2.0):
    m.mav.param_request_read_send(1, 1, name.encode(), -1)
    end = time.time() + timeout
    while time.time() < end:
        msg = m.recv_match(type="PARAM_VALUE", blocking=True, timeout=0.5)
        if msg and msg.param_id == name:
            return msg
    return None

def set_one(m, name, value, ptype, timeout=2.0):
    m.mav.param_set_send(1, 1, name.encode(), encode(value, ptype), ptype)
    end = time.time() + timeout
    while time.time() < end:
        msg = m.recv_match(type="PARAM_VALUE", blocking=True, timeout=0.5)
        if msg and msg.param_id == name:
            return msg
    return None

def fmt(v, ptype):
    return str(int(v)) if ptype in INT_TYPES else f"{v:.18f}"

def save(out, sets):
    m = connect()
    if sets:
        cur = fetch_all(m)
        for s in sets:
            name, value = s.split("=")
            ptype = cur[name][1]
            r = set_one(m, name, value, ptype)
            assert r is not None, f"set {name} failed"
            print(f"set {name} = {decode(r)}")
    params = fetch_all(m)
    with open(out, "w") as f:
        f.write("# Onboard parameters for Vehicle 1\n#\n# Vehicle-Id Component-Id Name Value Type\n")
        for name in sorted(params):
            v, t, _ = params[name]
            f.write(f"1\t1\t{name}\t{fmt(v, t)}\t{t}\n")
    print(f"saved {len(params)} parameters to {out}")

def load(inp, report):
    m = connect()
    vehicle = fetch_all(m)
    rows = []
    for line in open(inp):
        if line.startswith("#") or not line.strip():
            continue
        _, _, name, value, ptype = line.rstrip("\n").split("\t")
        ptype = int(ptype)
        fv = int(value) if ptype in INT_TYPES else float(value)
        if name not in vehicle:
            # QGC would not send it ("not found on the Vehicle and cannot be sent"); we send it anyway to show the firmware result
            r = set_one(m, name, fv, ptype)
            rows.append((name, value, "NOT_ON_VEHICLE", "accepted" if r else "no reply"))
            continue
        vv, vt, _ = vehicle[name]
        same = (vv == fv) if ptype in INT_TYPES else abs(vv - fv) <= 1e-6 * max(1.0, abs(fv))
        if same:
            rows.append((name, value, "UNCHANGED", ""))
            continue
        r = set_one(m, name, fv, vt)
        rows.append((name, value, "SENT", f"now {decode(r)}" if r else "no reply"))
    with open(report, "w") as f:
        for row in rows:
            f.write("\t".join(map(str, row)) + "\n")
    from collections import Counter
    print(Counter(r[2] for r in rows))
    for r in rows:
        if r[2] != "UNCHANGED":
            print("  ", *r)

if __name__ == "__main__":
    if sys.argv[1] == "save":
        save(sys.argv[2], sys.argv[3:])
    elif sys.argv[1] == "load":
        load(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == "read":
        m = connect()
        for n in sys.argv[2].split(","):
            r = read_one(m, n)
            print(n, "=", decode(r) if r else "NOT FOUND")
