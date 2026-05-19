import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import random
import time
from datetime import datetime

# ==================================================
# PAGE SETUP
# ==================================================
st.set_page_config(
    page_title="Interactive Smart Shower ",
    page_icon="🚿",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==================================================
# STYLING
# ==================================================
st.markdown(
    """
    <style>
    .stApp {
        background: radial-gradient(circle at top left, #102a43 0%, #0b1120 40%, #020617 100%);
        color: #e5e7eb;
    }

    .hero {
        padding: 24px 30px;
        border-radius: 28px;
        background: linear-gradient(135deg, #0f172a 0%, #1d4ed8 58%, #06b6d4 100%);
        color: white;
        box-shadow: 0 20px 55px rgba(0,0,0,0.35);
        margin-bottom: 18px;
    }

    .hero h1 {
        font-size: 38px;
        font-weight: 900;
        margin: 0 0 8px 0;
    }

    .hero p {
        font-size: 16px;
        margin: 0;
        opacity: 0.92;
    }

    .status-ok {
        background: #dcfce7;
        color: #166534;
        padding: 8px 14px;
        border-radius: 999px;
        font-weight: 800;
        display: inline-block;
        margin-top: 12px;
    }

    .status-warn {
        background: #fef3c7;
        color: #92400e;
        padding: 8px 14px;
        border-radius: 999px;
        font-weight: 800;
        display: inline-block;
        margin-top: 12px;
    }

    .status-danger {
        background: #fee2e2;
        color: #991b1b;
        padding: 8px 14px;
        border-radius: 999px;
        font-weight: 800;
        display: inline-block;
        margin-top: 12px;
    }

    div[data-testid="stMetric"] {
        background: rgba(255,255,255,0.97);
        color: #0f172a !important;
        border-radius: 20px;
        padding: 14px;
        border: 1px solid rgba(148,163,184,0.30);
        box-shadow: 0 10px 25px rgba(0,0,0,0.16);
    }

    div[data-testid="stMetric"] * {
        color: #0f172a !important;
    }

    .stButton > button {
        border-radius: 16px;
        min-height: 44px;
        font-weight: 800;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ==================================================
# BASIC HELPERS
# ==================================================
def clamp(value, low, high):
    return max(low, min(value, high))


def mix_temperature(hot_valve, cold_valve, hot_temp, cold_temp):
    total = hot_valve + cold_valve
    if total <= 0:
        return cold_temp
    return ((hot_valve * hot_temp) + (cold_valve * cold_temp)) / total


def ideal_valves(target, hot_temp, cold_temp, flow):
    if hot_temp <= cold_temp:
        return 0.0, float(flow)

    hot_ratio = (target - cold_temp) / (hot_temp - cold_temp)
    hot_ratio = clamp(hot_ratio, 0, 1)
    cold_ratio = 1 - hot_ratio
    return round(flow * hot_ratio, 1), round(flow * cold_ratio, 1)


def temp_color(temp):
    ratio = clamp((temp - 25) / 22, 0, 1)
    r = int(30 + 225 * ratio)
    g = int(150 - 55 * ratio)
    b = int(255 - 225 * ratio)
    return f"rgb({r},{g},{b})"


def status_label():
    if st.session_state.safety:
        return "ANTI-SCALD SHUTOFF", "status-danger"
    if not st.session_state.running:
        return "TAP CLOSED", "status-warn"

    diff = abs(st.session_state.target - st.session_state.outlet_temp)
    if diff <= 0.4:
        return "TEMPERATURE LOCKED", "status-ok"
    if st.session_state.outlet_temp < st.session_state.target:
        return "WARMING TO TARGET", "status-warn"
    return "COOLING TO TARGET", "status-warn"


def current_decision_text():
    error = st.session_state.target - st.session_state.outlet_temp

    if st.session_state.safety:
        return "Unsafe temperature detected. The controller closes the hot valve and opens cold water."
    if not st.session_state.running:
        return "Tap is closed. The selected temperature is saved for the next start."
    if abs(error) <= 0.4:
        return "Outlet temperature is close to target. The controller makes small balancing corrections."
    if error > 0:
        return "Outlet water is too cold. The controller opens the hot valve and reduces cold flow."
    return "Outlet water is too hot. The controller reduces the hot valve and opens cold flow."


def real_world_scenario_text():
    scenario = st.session_state.last_scenario

    if "Hot tank temperature dropped" in scenario:
        return (
            "Real-world example: the water heater is running out of hot water, the heater is undersized, "
            "or many people used hot water before this shower. The hot line is still flowing, but it is not hot enough."
        )

    if "Hot tank temperature rose" in scenario:
        return (
            "Real-world example: the heater thermostat is set too high or the heater recovered after being cold. "
            "The hot line now carries stronger/hotter water than before."
        )

    if "Cold supply became colder" in scenario:
        return (
            "Real-world example: cold water from the municipal line or storage tank becomes cooler after rain, at night, "
            "or because water is coming from a colder underground/source supply."
        )

    if "Cold supply became warmer" in scenario:
        return (
            "Real-world example: cold water in a rooftop tank warms under the sun, or pipes running through a hot ceiling/roof space warm the cold supply. "
            "This is common in hot climates."
        )

    if "Hot pressure drop" in scenario:
        return (
            "Real-world example: someone opens another hot tap, a washing machine starts using hot water, "
            "or the hot water line has low pump pressure. Less hot water reaches the shower mixer."
        )

    if "Cold pressure drop" in scenario:
        return (
            "Real-world example: someone flushes a toilet, opens another cold tap, or a pump/tank cannot supply enough cold water. "
            "Less cold water reaches the shower mixer, so the outlet can suddenly become hotter."
        )

    if "Overheat safety" in scenario or "Anti-scald" in scenario:
        return (
            "Real-world example: the heater overheats, the cold supply suddenly fails, or the hot valve sticks open. "
            "The anti-scald function protects the person by shutting hot water and opening cold water."
        )

    if "Tap opened" in scenario:
        return (
            "Real-world example: the person opens the shower. The controller first estimates the correct hot/cold mix, "
            "then uses the outlet sensor to fine-tune the temperature."
        )

    if "Tap closed" in scenario:
        return (
            "Real-world example: the person closes the shower. The controller stops actively mixing, but remembers the selected temperature for next time."
        )

    return (
        "Real-world example: normal shower operation. Small pressure and temperature changes happen naturally in plumbing, "
        "so the controller keeps adjusting the valves to hold the selected temperature."
    )


def why_valves_changed():
    error = st.session_state.target - st.session_state.outlet_temp
    scenario = st.session_state.last_scenario

    if st.session_state.safety:
        return "The outlet temperature reached the anti-scald limit. Safety overrides comfort control: hot water closes and cold water opens."

    if not st.session_state.running:
        return "The tap is closed, so the controller is not actively mixing water."

    if "Hot tank temperature dropped" in scenario:
        return "The hot tank temperature dropped. Hot water is now weaker, so the controller must open the hot valve more to keep the outlet near target."

    if "Hot tank temperature rose" in scenario:
        return "The hot tank temperature rose. Hot water is now stronger, so the controller should reduce the hot valve and use more cold water."

    if "Cold supply became colder" in scenario:
        return "The cold supply became colder. Cold water now cools the mix more strongly, so the controller uses less cold water and more hot water."

    if "Cold supply became warmer" in scenario:
        return "The cold supply became warmer. Cold water no longer cools the mix as much, so the controller can use more cold water and less hot water."

    if "Hot pressure drop" in scenario:
        return "Hot pressure dropped, so less hot water reached the mixer. The outlet cools, then the controller opens the hot valve to recover."

    if "Cold pressure drop" in scenario:
        return "Cold pressure dropped, so less cold water reached the mixer. The outlet warms up, then the controller opens the cold valve and reduces hot flow."

    if abs(error) <= 0.4:
        return "The outlet is already near the selected temperature, so only small valve changes are needed."

    if error > 0:
        return "The outlet is below the selected temperature, so the system needs more heat from the hot line."

    return "The outlet is above the selected temperature, so the system needs more cooling from the cold line."


def student_question_prompt():
    scenario = st.session_state.last_scenario

    if "Hot pressure drop" in scenario:
        return "Student question: Why did the outlet temperature fall first, and why did the hot valve percentage increase afterward?"

    if "Cold pressure drop" in scenario:
        return "Student question: Why can a loss of cold pressure make the shower hotter, and why is anti-scald protection important?"

    if "Hot tank temperature dropped" in scenario:
        return "Student question: Why does the controller need more hot valve opening when the hot tank temperature is lower?"

    if "Hot tank temperature rose" in scenario:
        return "Student question: Why can the same hot valve opening become too hot when the heater temperature rises?"

    if "Cold supply became colder" in scenario:
        return "Student question: Why does colder cold water require a different mixing ratio?"

    if "Cold supply became warmer" in scenario:
        return "Student question: Why does warmer cold water make cooling less effective?"

    if "Overheat" in scenario or "Anti-scald" in scenario:
        return "Student question: Why does safety shutoff override the user’s selected temperature?"

    return "Student question: How does the controller decide whether to open the hot valve or the cold valve?"


# ==================================================
# 3D SCENE HELPERS
# ==================================================
def sphere(cx, cy, cz, r, n=20):
    u = np.linspace(0, 2 * np.pi, n)
    v = np.linspace(0, np.pi, n)
    x = cx + r * np.outer(np.cos(u), np.sin(v))
    y = cy + r * np.outer(np.sin(u), np.sin(v))
    z = cz + r * np.outer(np.ones(np.size(u)), np.cos(v))
    return x, y, z


def add_line(fig, x, y, z, color, width=6, opacity=1):
    fig.add_trace(
        go.Scatter3d(
            x=x,
            y=y,
            z=z,
            mode="lines",
            line=dict(color=color, width=width),
            opacity=opacity,
            showlegend=False,
        )
    )


def make_scene():
    target = st.session_state.target
    outlet = st.session_state.outlet_temp
    hot_v = st.session_state.hot_valve
    cold_v = st.session_state.cold_valve
    running = st.session_state.running and not st.session_state.safety
    flow = st.session_state.flow

    fig = go.Figure()
    W, D, H = 2.5, 2.25, 2.8

    fig.add_trace(go.Surface(
        x=np.array([[0, W], [0, W]]),
        y=np.array([[0, 0], [D, D]]),
        z=np.array([[0, 0], [0, 0]]),
        colorscale=[[0, "#e2e8f0"], [1, "#94a3b8"]],
        showscale=False,
        opacity=0.95,
    ))

    fig.add_trace(go.Surface(
        x=np.array([[0, W], [0, W]]),
        y=np.array([[D, D], [D, D]]),
        z=np.array([[0, 0], [H, H]]),
        colorscale=[[0, "#dbeafe"], [1, "#bfdbfe"]],
        showscale=False,
        opacity=0.35,
    ))

    for xval in [0, W]:
        fig.add_trace(go.Surface(
            x=np.array([[xval, xval], [xval, xval]]),
            y=np.array([[0, D], [0, D]]),
            z=np.array([[0, 0], [H, H]]),
            colorscale=[[0, "#e0f2fe"], [1, "#7dd3fc"]],
            showscale=False,
            opacity=0.18,
        ))

    frame = "#94a3b8"
    for ex, ey, ez in [
        ([0, 0], [0, 0], [0, H]),
        ([W, W], [0, 0], [0, H]),
        ([0, W], [0, 0], [H, H]),
        ([0, W], [0, 0], [0, 0]),
    ]:
        add_line(fig, ex, ey, ez, frame, 5)

    sx, sy, sz = W / 2, D - 0.18, H - 0.28
    add_line(fig, [sx, sx], [D, sy], [H - 0.05, sz], "#64748b", 10)
    fig.add_trace(go.Scatter3d(x=[sx], y=[sy], z=[sz], mode="markers", marker=dict(size=20, color="#334155"), showlegend=False))

    px, py = W / 2, 0.95
    hx, hy, hz = sphere(px, py, 1.78, 0.15)
    fig.add_trace(go.Surface(x=hx, y=hy, z=hz, colorscale=[[0, "#c08457"], [1, "#c08457"]], showscale=False))
    add_line(fig, [px, px], [py, py], [1.12, 1.60], "#0f766e", 18)
    add_line(fig, [px - 0.28, px + 0.28], [py, py], [1.45, 1.45], "#c08457", 10)
    add_line(fig, [px, px - 0.13], [py, py], [1.12, 0.15], "#c08457", 10)
    add_line(fig, [px, px + 0.13], [py, py], [1.12, 0.15], "#c08457", 10)

    if running and flow > 0:
        water = temp_color(outlet)
        count = max(8, int(flow / 2.3))
        for _ in range(count):
            dx = random.uniform(-0.38, 0.38)
            dy = random.uniform(-0.12, 0.18)
            add_line(
                fig,
                [sx + dx * 0.12, px + dx * 0.65],
                [sy, py + dy],
                [sz - 0.05, random.uniform(0.30, 0.70)],
                water,
                3,
                0.75,
            )

        fig.add_trace(go.Scatter3d(
            x=[px + random.uniform(-0.42, 0.42) for _ in range(35)],
            y=[py + random.uniform(-0.35, 0.35) for _ in range(35)],
            z=[random.uniform(0.02, 0.12) for _ in range(35)],
            mode="markers",
            marker=dict(size=3, color=water, opacity=0.55),
            showlegend=False,
        ))

    fig.add_trace(go.Scatter3d(
        x=[W - 0.25], y=[D - 0.04], z=[1.42],
        mode="markers+text",
        marker=dict(size=24, color="#0f172a"),
        text=[f"{target:.1f}°C"],
        textposition="middle right",
        textfont=dict(color="#0f172a", size=14),
        showlegend=False,
    ))

    add_line(fig, [0.22, 0.22], [0.16, 0.16], [0.15, 0.15 + hot_v / 100 * 1.2], "#ef4444", 13)
    add_line(fig, [0.42, 0.42], [0.16, 0.16], [0.15, 0.15 + cold_v / 100 * 1.2], "#3b82f6", 13)

    fig.add_trace(go.Scatter3d(
        x=[0.22, 0.42], y=[0.16, 0.16], z=[1.55, 1.55],
        mode="text",
        text=["HOT", "COLD"],
        textfont=dict(size=11, color="#0f172a"),
        showlegend=False,
    ))

    fig.update_layout(
        height=620,
        margin=dict(l=0, r=0, t=0, b=0),
        scene=dict(
            xaxis=dict(visible=False, range=[-0.25, W + 0.25]),
            yaxis=dict(visible=False, range=[-0.30, D + 0.25]),
            zaxis=dict(visible=False, range=[0, H + 0.15]),
            aspectmode="manual",
            aspectratio=dict(x=1.1, y=1, z=1.35),
            camera=dict(eye=dict(x=1.7, y=-2.15, z=1.25)),
            bgcolor="rgba(255,255,255,0)",
        ),
        paper_bgcolor="rgba(255,255,255,0)",
        showlegend=False,
    )
    return fig


# ==================================================
# STATE
# ==================================================
def init_state():
    defaults = {
        "running": False,
        "target": 38.0,
        "outlet_temp": 28.0,
        "hot_valve": 45.0,
        "cold_valve": 35.0,
        "flow": 80,
        "hot_supply": 60.0,
        "cold_supply": 25.0,
        "base_hot_supply": 60.0,
        "base_cold_supply": 25.0,
        "anti_scald": 46.0,
        "safety": False,
        "history": [],
        "step": 0,
        "hot_drop_steps": 0,
        "cold_drop_steps": 0,
        "hot_tank_drop_steps": 0,
        "hot_tank_rise_steps": 0,
        "cold_supply_colder_steps": 0,
        "cold_supply_warmer_steps": 0,
        "overheat_trigger": False,
        "last_scenario": "None",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_state()

# ==================================================
# SIMULATION LOGIC
# ==================================================
def simulate_one_step():
    hot_pressure = 1.0
    cold_pressure = 1.0

    # Environment gradually returns to normal when scenarios end.
    st.session_state.hot_supply += (st.session_state.base_hot_supply - st.session_state.hot_supply) * 0.015
    st.session_state.cold_supply += (st.session_state.base_cold_supply - st.session_state.cold_supply) * 0.015

    if st.session_state.hot_tank_drop_steps > 0:
        st.session_state.hot_supply += (48.0 - st.session_state.hot_supply) * 0.18
        st.session_state.hot_tank_drop_steps -= 1
        st.session_state.last_scenario = "Hot tank temperature dropped"

    if st.session_state.hot_tank_rise_steps > 0:
        st.session_state.hot_supply += (70.0 - st.session_state.hot_supply) * 0.18
        st.session_state.hot_tank_rise_steps -= 1
        st.session_state.last_scenario = "Hot tank temperature rose"

    if st.session_state.cold_supply_colder_steps > 0:
        st.session_state.cold_supply += (18.0 - st.session_state.cold_supply) * 0.18
        st.session_state.cold_supply_colder_steps -= 1
        st.session_state.last_scenario = "Cold supply became colder"

    if st.session_state.cold_supply_warmer_steps > 0:
        st.session_state.cold_supply += (32.0 - st.session_state.cold_supply) * 0.18
        st.session_state.cold_supply_warmer_steps -= 1
        st.session_state.last_scenario = "Cold supply became warmer"

    hot_supply_now = st.session_state.hot_supply
    cold_supply_now = st.session_state.cold_supply

    if st.session_state.safety:
        st.session_state.hot_valve = 0
        st.session_state.cold_valve = st.session_state.flow
        st.session_state.outlet_temp += (st.session_state.cold_supply - st.session_state.outlet_temp) * 0.25

        if st.session_state.outlet_temp <= st.session_state.target + 0.4:
            st.session_state.safety = False
            st.session_state.running = False
            st.session_state.last_scenario = "Safety cooled. Tap closed."

    elif st.session_state.running:
        hot_supply_now += random.uniform(-0.5, 0.5)
        cold_supply_now += random.uniform(-0.2, 0.2)
        hot_pressure = random.uniform(0.98, 1.02)
        cold_pressure = random.uniform(0.98, 1.02)

        if st.session_state.hot_drop_steps > 0:
            hot_pressure *= 0.55
            st.session_state.hot_drop_steps -= 1
            st.session_state.last_scenario = "Hot pressure drop active"

        if st.session_state.cold_drop_steps > 0:
            cold_pressure *= 0.55
            st.session_state.cold_drop_steps -= 1
            st.session_state.last_scenario = "Cold pressure drop active"

        if st.session_state.overheat_trigger:
            hot_supply_now += 18
            st.session_state.hot_valve = max(st.session_state.hot_valve, st.session_state.flow * 0.85)
            st.session_state.cold_valve = min(st.session_state.cold_valve, st.session_state.flow * 0.15)
            st.session_state.overheat_trigger = False
            st.session_state.last_scenario = "Overheat safety test triggered"

        actual_mix = mix_temperature(
            st.session_state.hot_valve * hot_pressure,
            st.session_state.cold_valve * cold_pressure,
            hot_supply_now,
            cold_supply_now,
        )

        st.session_state.outlet_temp += (actual_mix - st.session_state.outlet_temp) * 0.35

        if st.session_state.outlet_temp >= st.session_state.anti_scald:
            st.session_state.safety = True
            st.session_state.running = False
            st.session_state.hot_valve = 0
            st.session_state.cold_valve = st.session_state.flow
            st.session_state.last_scenario = "Anti-scald protection activated"
        else:
            error = st.session_state.target - st.session_state.outlet_temp
            correction = clamp(error * 1.4, -6, 6)
            st.session_state.hot_valve += correction
            st.session_state.cold_valve -= correction

            total = max(1, st.session_state.hot_valve + st.session_state.cold_valve)
            st.session_state.hot_valve = clamp(st.session_state.hot_valve / total * st.session_state.flow, 0, st.session_state.flow)
            st.session_state.cold_valve = clamp(st.session_state.cold_valve / total * st.session_state.flow, 0, st.session_state.flow)

    else:
        st.session_state.outlet_temp += (st.session_state.cold_supply - st.session_state.outlet_temp) * 0.04

    st.session_state.outlet_temp = round(st.session_state.outlet_temp, 2)
    st.session_state.hot_supply = round(st.session_state.hot_supply, 2)
    st.session_state.cold_supply = round(st.session_state.cold_supply, 2)
    st.session_state.hot_valve = round(st.session_state.hot_valve, 2)
    st.session_state.cold_valve = round(st.session_state.cold_valve, 2)
    st.session_state.step += 1

    error_now = st.session_state.target - st.session_state.outlet_temp

    st.session_state.history.append({
        "step": st.session_state.step,
        "time": datetime.now().strftime("%H:%M:%S"),
        "target": round(st.session_state.target, 2),
        "outlet_temp": round(st.session_state.outlet_temp, 2),
        "error": round(error_now, 2),
        "hot_valve_%": round(st.session_state.hot_valve, 1),
        "cold_valve_%": round(st.session_state.cold_valve, 1),
        "hot_supply_temp": round(st.session_state.hot_supply, 1),
        "cold_supply_temp": round(st.session_state.cold_supply, 1),
        "hot_pressure": round(hot_pressure, 2),
        "cold_pressure": round(cold_pressure, 2),
        "scenario": st.session_state.last_scenario,
        "status": status_label()[0],
        "decision": current_decision_text(),
    })
    st.session_state.history = st.session_state.history[-150:]


# ==================================================
# SIDEBAR CONTROLS
# ==================================================
# ==================================================
# SIDEBAR CONTROLS
# ==================================================
with st.sidebar:
    st.title("🚿 Smart Shower Panel")
    st.caption("A real-life digital shower control screen.")

    panel_status = "RUNNING" if st.session_state.running else "STANDBY"
    if st.session_state.safety:
        panel_status = "SAFETY SHUTOFF"

    st.markdown(
        f"""
        <div style="
            background: linear-gradient(180deg, #020617 0%, #111827 100%);
            color: #e5e7eb;
            padding: 18px;
            border-radius: 22px;
            border: 1px solid rgba(148,163,184,0.35);
            box-shadow: inset 0 0 24px rgba(14,165,233,0.16);
            text-align: center;
            margin-bottom: 12px;
        ">
            <div style="
                font-size: 12px;
                color: #93c5fd;
                text-transform: uppercase;
                letter-spacing: 1px;
            ">
                Set Temperature
            </div>
            <div style="
                font-size: 46px;
                font-weight: 900;
                letter-spacing: -1px;
                color: #f8fafc;
            ">
                {st.session_state.target:.1f}°C
            </div>
            <div style="
                margin-top: 8px;
                font-size: 13px;
                color: #cbd5e1;
            ">
                System: {panel_status}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Temperature Presets")
    preset1, preset2, preset3 = st.columns(3)

    with preset1:
        if st.button("Cool\n34°C", use_container_width=True):
            st.session_state.target = 34.0
            st.rerun()

    with preset2:
        if st.button("Comfy\n38°C", use_container_width=True):
            st.session_state.target = 38.0
            st.rerun()

    with preset3:
        if st.button("Warm\n41°C", use_container_width=True):
            st.session_state.target = 41.0
            st.rerun()

    adjust1, adjust2, adjust3 = st.columns([1, 1.2, 1])

    with adjust1:
        if st.button("− 0.5°C", use_container_width=True):
            st.session_state.target = clamp(st.session_state.target - 0.5, 30.0, 45.0)
            st.rerun()
    with adjust2:
        st.markdown(
            f"<div style='text-align:center; padding-top:10px; font-weight:800;'>{st.session_state.target:.1f}°C</div>",
            unsafe_allow_html=True,
        )

    with adjust3:
        if st.button("+ 0.5°C", use_container_width=True):
            st.session_state.target = clamp(st.session_state.target + 0.5, 30.0, 45.0)

    st.divider()

    st.markdown("### Flow Setting")
    flow1, flow2, flow3 = st.columns(3)

    with flow1:
        if st.button("Low", use_container_width=True):
            st.session_state.flow = 40

    with flow2:
        if st.button("Mid", use_container_width=True):
            st.session_state.flow = 70

    with flow3:
        if st.button("High", use_container_width=True):
            st.session_state.flow = 100

    st.progress(st.session_state.flow / 100, text=f"Current flow: {st.session_state.flow}%")

    st.divider()

    st.markdown("### Tap Control")
    tap1, tap2 = st.columns(2)

    with tap1:
        if st.button("🚿 Open Tap", use_container_width=True):
            st.session_state.running = True
            st.session_state.safety = False
            st.session_state.last_scenario = "Tap opened"
            st.session_state.hot_valve, st.session_state.cold_valve = ideal_valves(
                st.session_state.target,
                st.session_state.hot_supply,
                st.session_state.cold_supply,
                st.session_state.flow,
            )

    with tap2:
        if st.button("⏸ Close Tap", use_container_width=True):
            st.session_state.running = False
            st.session_state.last_scenario = "Tap closed"

    st.divider()

    st.title("System Scenarios")
    st.caption("Simulate realistic water supply changes while the shower is running.")

    if st.button("Hot tank temperature drops", use_container_width=True):
        st.session_state.hot_tank_drop_steps = 35
        st.session_state.last_scenario = "Hot tank temperature dropped"

    if st.button("Hot tank temperature rises", use_container_width=True):
        st.session_state.hot_tank_rise_steps = 35
        st.session_state.last_scenario = "Hot tank temperature rose"

    if st.button("Cold supply becomes colder", use_container_width=True):
        st.session_state.cold_supply_colder_steps = 35
        st.session_state.last_scenario = "Cold supply became colder"

    if st.button("Cold supply becomes warmer", use_container_width=True):
        st.session_state.cold_supply_warmer_steps = 35
        st.session_state.last_scenario = "Cold supply became warmer"

    if st.button("Hot pressure drop", use_container_width=True):
        st.session_state.hot_drop_steps = 16
        st.session_state.last_scenario = "Hot pressure drop selected"

    if st.button("Cold pressure drop", use_container_width=True):
        st.session_state.cold_drop_steps = 16
        st.session_state.last_scenario = "Cold pressure drop selected"

    if st.button("Overheat safety test", use_container_width=True):
        st.session_state.overheat_trigger = True
        st.session_state.last_scenario = "Overheat safety test selected"

    st.divider()

    st.subheader("Safety Limit")
    st.session_state.anti_scald = st.slider(
        "Anti-scald shutoff temperature",
        42.0,
        50.0,
        st.session_state.anti_scald,
        0.5,
    )

    if st.button("Reset system", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
# ==================================================
# SIMULATE BEFORE DISPLAYING VALUES
# ==================================================
if st.session_state.running or st.session_state.safety:
    simulate_one_step()

error = st.session_state.target - st.session_state.outlet_temp
label, css_class = status_label()

# ==================================================
# MAIN PAGE
# ==================================================
st.markdown(
    f"""
    <div class="hero">
        <h1>🚿 Interactive Smart Shower</h1>
        <p>The student controls only temperature, flow, and tap position. The instructor creates supply faults to show how the controller adjusts hot and cold valves.</p>
        <span class="{css_class}">{label}</span>
    </div>
    """,
    unsafe_allow_html=True,
)

# Compact dashboard metrics
st.subheader("Live Dashboard")
metric_row1 = st.columns(4)
with metric_row1[0]:
    st.metric("Desired Temp", f"{st.session_state.target:.1f} °C")
with metric_row1[1]:
    st.metric("Outlet Sensor", f"{st.session_state.outlet_temp:.1f} °C")
with metric_row1[2]:
    st.metric("Control Error", f"{error:.2f} °C")
with metric_row1[3]:
    st.metric("Simulation Step", st.session_state.step)

metric_row2 = st.columns(4)
with metric_row2[0]:
    st.metric("Hot Valve", f"{st.session_state.hot_valve:.1f}%")
with metric_row2[1]:
    st.metric("Cold Valve", f"{st.session_state.cold_valve:.1f}%")
with metric_row2[2]:
    st.metric("Hot Tank Supply", f"{st.session_state.hot_supply:.1f} °C")
with metric_row2[3]:
    st.metric("Cold Supply", f"{st.session_state.cold_supply:.1f} °C")

# Training explanation panel
learning_col1, learning_col2 = st.columns([1.05, 1], gap="large")

with learning_col1:
    with st.container(border=True):
        st.subheader("Real-world scenario")
        st.write(real_world_scenario_text())
        st.info(student_question_prompt())
        st.caption(f"Active scenario: {st.session_state.last_scenario}")

with learning_col2:
    with st.container(border=True):
        st.subheader("Why did the valves change?")
        st.write(why_valves_changed())
        st.divider()
        st.subheader("Controller decision")
        if st.session_state.safety:
            st.error(current_decision_text())
        elif not st.session_state.running:
            st.warning(current_decision_text())
        elif abs(error) <= 0.4:
            st.success(current_decision_text())
        elif error > 0:
            st.info(current_decision_text())
        else:
            st.info(current_decision_text())

# Scene and graphs
scene_col, graph_col = st.columns([1.55, 1], gap="large")

with scene_col:
    with st.container(border=True):
        st.subheader("3D Shower View")
        st.caption("Falling water shows mixed outlet water. Red and blue bars show hot and cold valve openings.")
        st.plotly_chart(make_scene(), use_container_width=True)

with graph_col:
    with st.container(border=True):
        st.subheader("Temperature Over Time")
        df = pd.DataFrame(st.session_state.history)
        if not df.empty:
            st.line_chart(df.set_index("step")[["target", "outlet_temp", "hot_supply_temp", "cold_supply_temp"]])
            st.subheader("Valve Movement")
            st.line_chart(df.set_index("step")[["hot_valve_%", "cold_valve_%"]])
        else:
            st.info("Open the tap to start collecting data.")

with st.container(border=True):
    st.subheader("Live System Log")
    st.caption("Exercise: open the tap, wait for temperature lock, trigger a supply scenario, then explain the real-world cause and why the valve percentages changed.")
    if st.session_state.history:
        st.dataframe(pd.DataFrame(st.session_state.history).tail(15), use_container_width=True, hide_index=True)
    else:
        st.info("No data yet. Open the tap to start the simulation.")

# ==================================================
# CONTINUOUS RUN WHEN TAP IS OPEN
# ==================================================
if st.session_state.running or st.session_state.safety:
    time.sleep(0.25)
    st.rerun()