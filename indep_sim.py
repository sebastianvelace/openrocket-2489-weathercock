#!/usr/bin/env python3
"""
Independent planar (pitch-plane) rocket simulator for the TRF #2489 rocket.

Purpose: check, outside OpenRocket's code, that the high-wind downturn of the upwind distance
follows from the body crossflow lift term and not from some other part of OpenRocket.

Written from the physical equations, not from OpenRocket's source:
  * translation in the vertical X-Z plane + pitch rotation, RK4 integration
  * ISA atmosphere (own implementation)
  * launch rail: motion constrained along the vertical rail until the rocket has travelled RAIL m
  * normal force: nose potential lift CNa=2 at the Barrowman ogive CP (0.466 L_nose),
    body crossflow K*(Ap/Aref)*sin^2(alpha) at the planform centroid,
    fins CNa(M)*min(alpha, stall) at the Barrowman fin CP
  * pitch damping: body crossflow damping (0.275 = 1.1/4 form) + fin damping, as in the techdoc model
  * jet damping: -mdot * (x_nozzle - x_cg)^2 * q
  * axial force: CA(M) * qdyn * Aref along the axis

Time-dependent mass properties and thrust, the axial drag coefficient table and the fin CNa(M)
table are read from OpenRocket output (they are inputs, like a motor file or a wind tunnel table;
none of them is the quantity under test). Everything else is computed here.

Wind convention matches OpenRocket: airspeed = v + (W, 0), so +X is upwind.
"""
import csv
import glob
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- geometry (from test01.ork)
L_NOSE = 0.3429
R_BODY = 0.033655
D_BODY = 2 * R_BODY
L_CYL = 0.4064 + 0.0270002 + 0.817999
L_BODY = L_NOSE + L_CYL
A_REF = math.pi * R_BODY ** 2
L_REF = D_BODY
N_FINS = 3
FIN_ROOT, FIN_TIP, FIN_SPAN, FIN_SWEEP = 0.248001, 0.0799998, 0.0689991, 0.14797
FIN_LE = L_BODY - 0.018001 - FIN_ROOT          # root leading edge from nose tip
X_NOZZLE = L_BODY + 0.0127                     # motor overhang
STALL = math.radians(20.0)


def ogive_planform():
    rho = (R_BODY ** 2 + L_NOSE ** 2) / (2 * R_BODY)
    n = 20000
    area = mom = 0.0
    for i in range(n):
        x = (i + 0.5) * L_NOSE / n
        r = math.sqrt(rho ** 2 - (L_NOSE - x) ** 2) + R_BODY - rho
        area += 2 * r * L_NOSE / n
        mom += 2 * r * x * L_NOSE / n
    return area, mom


_an, _mn = ogive_planform()
A_PLAN = _an + D_BODY * L_CYL
X_PLAN = (_mn + D_BODY * L_CYL * (L_NOSE + L_CYL / 2)) / A_PLAN
X_NOSE_CP = 0.466 * L_NOSE                      # Barrowman tangent-ogive CP
# Barrowman fin CP
X_FIN_CP = (FIN_LE + FIN_SWEEP * (FIN_ROOT + 2 * FIN_TIP) / (3 * (FIN_ROOT + FIN_TIP))
            + (FIN_ROOT + FIN_TIP - FIN_ROOT * FIN_TIP / (FIN_ROOT + FIN_TIP)) / 6)
A_FIN = 0.5 * (FIN_ROOT + FIN_TIP) * FIN_SPAN
# fin planform centroid along the axis (for the fin damping arm)
X_FIN_MID = FIN_LE + (FIN_SWEEP * (FIN_ROOT + 2 * FIN_TIP) + (FIN_ROOT ** 2 + FIN_ROOT * FIN_TIP + FIN_TIP ** 2)) / (3 * (FIN_ROOT + FIN_TIP))
D_AVG = A_PLAN / L_BODY


def barrowman_fin_cna_subsonic(interference_squared):
    mid = math.hypot(FIN_SPAN, FIN_SWEEP + (FIN_TIP - FIN_ROOT) / 2)
    cna = 4 * N_FINS * (FIN_SPAN / D_BODY) ** 2 / (1 + math.sqrt(1 + (2 * mid / (FIN_ROOT + FIN_TIP)) ** 2))
    tau = R_BODY / (FIN_SPAN + R_BODY)
    return cna * ((1 + tau) ** 2 if interference_squared else (1 + tau))


# ---------------------------------------------------------------- atmosphere (ISA, troposphere)
def isa(h):
    t = 288.15 - 0.0065 * h
    p = 101325.0 * (t / 288.15) ** 5.25588
    rho = p / (287.053 * t)
    a = math.sqrt(1.4 * 287.053 * t)
    return rho, a


# ---------------------------------------------------------------- tables from OpenRocket output
def interp(xs, ys, x):
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    lo, hi = 0, len(xs) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if xs[mid] <= x:
            lo = mid
        else:
            hi = mid
    f = (x - xs[lo]) / (xs[hi] - xs[lo])
    return ys[lo] + f * (ys[hi] - ys[lo])


def load_inputs(ts_file, static_dir):
    rows = list(csv.reader(open(ts_file), delimiter="\t"))
    h = rows[0]
    data = [[float(v) for v in r] for r in rows[1:]]
    col = {name: i for i, name in enumerate(h)}

    def c(prefix):
        for name, i in col.items():
            if name.startswith(prefix):
                return [d[i] for d in data]
        raise KeyError(prefix)

    t = c("Time")
    tab = {
        "t": t, "thrust": c("Thrust"), "mass": c("Mass"), "cg": c("CG_location"),
        "iyy": c("Longitudinal_moment_of_inertia") if any(n.startswith("Longitudinal_moment") for n in col) else c("Longitudinal"),
        "mach": c("Mach_number"), "ca": c("Axial_drag_coefficient") if any(n.startswith("Axial_drag") for n in col) else c("Axial"),
        "g": c("Gravitational") if any(n.startswith("Gravitational") for n in col) else [9.80665] * len(t),
    }
    # axial drag coefficient as a function of Mach (zero-wind flight, monotonic part up to apogee)
    pairs = sorted(set((round(m, 4), ca) for m, ca in zip(tab["mach"], tab["ca"]) if m > 0.02 and not math.isnan(ca)))
    ms, cas = [], []
    for m, ca in pairs:
        if ms and abs(m - ms[-1]) < 1e-9:
            continue
        ms.append(m)
        cas.append(ca)
    tab["ca_mach"], tab["ca_val"] = ms, cas
    # fin CNa(M) from the static probe
    fm, fc = [], []
    for f in sorted(glob.glob(os.path.join(static_dir, "st_M*.tsv")), key=lambda p: float(os.path.basename(p)[4:-4])):
        m = float(os.path.basename(f)[4:-4])
        r = {int(x["aoa_deg"]): x for x in csv.DictReader(open(f), delimiter="\t")}
        fm.append(m)
        fc.append(float(r[2]["CN_fins"]) / math.radians(2))
    tab["fin_mach"], tab["fin_cna"] = fm, fc
    # mass flow from mass history
    tab["mdot"] = [0.0] * len(t)
    for i in range(1, len(t) - 1):
        tab["mdot"][i] = -(tab["mass"][i + 1] - tab["mass"][i - 1]) / (t[i + 1] - t[i - 1])
    return tab


# ---------------------------------------------------------------- dynamics
def simulate(tab, wind, k_body=1.1, k_damp=1.1, rail=2.4384, dt=0.002, tmax=40.0, fin_stall=True, jorgensen_potential=False):
    tt = tab["t"]
    x = z = vx = vz = theta = q = 0.0
    on_rail = True
    t = 0.0
    out = []

    def aero(state, t):
        x, z, vx, vz, th, q = state
        m = interp(tt, tab["mass"], t)
        cg = interp(tt, tab["cg"], t)
        iyy = interp(tt, tab["iyy"], t)
        thr = interp(tt, tab["thrust"], t)
        mdot = interp(tt, tab["mdot"], t)
        g = interp(tt, tab["g"], t)
        rho, a_snd = isa(max(z, 0.0))
        ax, az = math.sin(th), math.cos(th)
        rx, rz = vx + wind, vz                     # airspeed vector (OpenRocket convention)
        v = math.hypot(rx, rz)
        mach = v / a_snd
        qd = 0.5 * rho * v * v
        fx = thr * ax
        fz = thr * az - m * g
        torque = 0.0
        alpha = 0.0
        if v > 1e-6:
            cross = ax * rz - az * rx
            dot = ax * rx + az * rz
            alpha = math.atan2(abs(cross), dot)
            # axial coefficient vs time from the zero-wind run: CA differs powered/coasting (base drag)
            ca = interp(tt, tab["ca"], t)
            fx -= qd * A_REF * ca * ax
            fz -= qd * A_REF * ca * az
            # unit vector of the airspeed component normal to the axis
            px, pz = rx - dot * ax, rz - dot * az
            pn = math.hypot(px, pz)
            if pn > 1e-9:
                px, pz = px / pn, pz / pn
                s = math.sin(alpha)
                if jorgensen_potential:
                    cn_nose = math.sin(2 * alpha) * math.cos(alpha / 2)   # Jorgensen eq. (1), A_b = A_ref
                else:
                    cn_nose = 2.0 * s                              # slender-body potential lift (OpenRocket form)
                cn_cross = k_body * A_PLAN / A_REF * s * s
                cn_fin = interp(tab["fin_mach"], tab["fin_cna"], mach) * (min(alpha, STALL) if fin_stall else alpha)
                cm_nose_cg = 0.0
                for cn, xs in ((cn_nose, X_NOSE_CP), (cn_cross, X_PLAN), (cn_fin, X_FIN_CP)):
                    fnx, fnz = -qd * A_REF * cn * px, -qd * A_REF * cn * pz   # force opposes sideways motion
                    fx += fnx
                    fz += fnz
                    arm = cg - xs                                # >0: station ahead of CG
                    rxa, rza = arm * ax, arm * az
                    torque += rza * fnx - rxa * fnz
                # pitch damping (opposes q), techdoc-type model, clamped to the static moment
                if abs(q) > 1e-12:
                    lf, la = cg, L_BODY - cg
                    mul = 0.25 * k_damp * D_AVG * (lf ** 4 + la ** 4) / (A_REF * L_REF)
                    mul += 0.6 * min(N_FINS, 4) * A_FIN * abs(X_FIN_MID - cg) ** 3 / (A_REF * L_REF)
                    cmd = min(mul * (q / v) ** 2, abs(torque) / (qd * A_REF * L_REF) if qd > 0 else 0)
                    torque -= math.copysign(cmd * qd * A_REF * L_REF, q)
        # jet damping
        torque -= mdot * (X_NOZZLE - cg) ** 2 * q
        return fx / m, fz / m, torque / iyy, alpha, mach

    state = [x, z, vx, vz, theta, q]
    while t < tmax:
        def deriv(s, tt_):
            ax_, az_, qdot, _, _ = aero(s, tt_)
            if on_rail:
                # constrained along the vertical rail: only axial motion, no rotation, no lateral motion
                return [0.0, s[3], 0.0, max(az_, 0.0) if s[1] <= 1e-9 else az_, 0.0, 0.0]
            return [s[2], s[3], ax_, az_, s[5], qdot]

        k1 = deriv(state, t)
        k2 = deriv([s + dt / 2 * d for s, d in zip(state, k1)], t + dt / 2)
        k3 = deriv([s + dt / 2 * d for s, d in zip(state, k2)], t + dt / 2)
        k4 = deriv([s + dt * d for s, d in zip(state, k3)], t + dt)
        new = [s + dt / 6 * (a + 2 * b + 2 * c + d) for s, a, b, c, d in zip(state, k1, k2, k3, k4)]
        t += dt
        if on_rail and new[1] >= rail:
            on_rail = False
        _, _, _, alpha, mach = aero(new, t)
        out.append((t, new[0], new[1], new[2], new[3], new[4], new[5], alpha, mach))
        if not on_rail and new[3] < 0 and state[3] >= 0:
            break
        state = new
    return out


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else HERE
    tab = load_inputs(os.path.join(base, "inputs", "full_K1.1_0mph.tsv"), os.path.join(base, "inputs", "static"))
    print(f"geometry: L={L_BODY:.4f} l/d={L_BODY / D_BODY:.2f} Ap/Aref={A_PLAN / A_REF:.2f} x_plan={X_PLAN:.4f} "
          f"x_noseCP={X_NOSE_CP:.4f} x_finCP={X_FIN_CP:.4f}")
    print(f"Barrowman fin CNa: (1+tau) {barrowman_fin_cna_subsonic(False):.4f}, (1+tau)^2 {barrowman_fin_cna_subsonic(True):.4f}; "
          f"OpenRocket table at M={tab['fin_mach'][0]}: {tab['fin_cna'][0]:.4f}")
    cases = [("K=1.1 (OpenRocket)", dict(k_body=1.1, k_damp=1.1)),
             ("K=0.86 lift only", dict(k_body=0.86, k_damp=1.1)),
             ("K=0.86 lift+damp", dict(k_body=0.86, k_damp=0.86)),
             ("K=0 lift", dict(k_body=0.0, k_damp=1.1))]
    winds = [0, 5, 10, 15, 20, 25, 30]
    print("upwind at apogee, ft")
    print(f"{'case':22s}" + "".join(f"{w:>7d}" for w in winds))
    for name, kw in cases:
        row = []
        for w in winds:
            o = simulate(tab, w * 0.44704, **kw)
            row.append(o[-1][1] * 3.28084)
        print(f"{name:22s}" + "".join(f"{v:7.0f}" for v in row))
    o = simulate(tab, 0.0)
    print(f"apogee at 0 wind: {o[-1][2] * 3.28084:.0f} ft at t={o[-1][0]:.2f} s")
    o = simulate(tab, 30 * 0.44704)
    exit_rows = [r for r in o if r[2] >= 2.4384]
    print(f"30 mph: AoA just off rail {math.degrees(exit_rows[0][7]):.1f} deg, analytic atan(W/V) "
          f"{math.degrees(math.atan2(30 * 0.44704, math.hypot(exit_rows[0][3], exit_rows[0][4]) if False else exit_rows[0][4])):.1f} deg")


if __name__ == "__main__":
    main()
