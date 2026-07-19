import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from discovery import find_meeting, list_sessions
from drivers import get_drivers, drivers_championship, teams_championship
from events import get_overtakes, get_pit_stops, get_race_control, get_team_radio
from openf1_client import get as raw_get
from results import get_session_result, get_starting_grid
from timing import get_laps, get_stints
from weather import get_weather

st.set_page_config(page_title="F1 Race Weekend Analyzer", layout="wide")

CACHE_TTL = 3600  # seconds
COMPOUND_COLORS = {
    "SOFT": "#e10600",
    "MEDIUM": "#ffd12e",
    "HARD": "#f0f0f0",
    "INTERMEDIATE": "#43b02a",
    "WET": "#0067ad",
}

# ---------------------------------------------------------------------------
# Wrap every data-fetching function with Streamlit's cache so re-running the
# script on each widget interaction doesn't re-hit the API every time.
# ---------------------------------------------------------------------------
find_meeting = st.cache_data(ttl=CACHE_TTL)(find_meeting)
list_sessions = st.cache_data(ttl=CACHE_TTL)(list_sessions)
get_drivers = st.cache_data(ttl=CACHE_TTL)(get_drivers)
drivers_championship = st.cache_data(ttl=CACHE_TTL)(drivers_championship)
teams_championship = st.cache_data(ttl=CACHE_TTL)(teams_championship)
get_starting_grid = st.cache_data(ttl=CACHE_TTL)(get_starting_grid)
get_session_result = st.cache_data(ttl=CACHE_TTL)(get_session_result)
get_laps = st.cache_data(ttl=CACHE_TTL)(get_laps)
get_stints = st.cache_data(ttl=CACHE_TTL)(get_stints)
get_pit_stops = st.cache_data(ttl=CACHE_TTL)(get_pit_stops)
get_overtakes = st.cache_data(ttl=CACHE_TTL)(get_overtakes)
get_race_control = st.cache_data(ttl=CACHE_TTL)(get_race_control)
get_team_radio = st.cache_data(ttl=CACHE_TTL)(get_team_radio)
get_weather = st.cache_data(ttl=CACHE_TTL)(get_weather)
raw_get = st.cache_data(ttl=CACHE_TTL)(raw_get)


def df(records):
    return pd.DataFrame(records) if records else pd.DataFrame()


# ---------------------------------------------------------------------------
# Sidebar: pick a race weekend + session
# ---------------------------------------------------------------------------
st.sidebar.header("Race weekend")
year = st.sidebar.number_input("Year", min_value=2023, max_value=2026, value=2024, step=1)
country = st.sidebar.text_input("Country", value="Belgium")
load_clicked = st.sidebar.button("Load weekend", type="primary")

if load_clicked:
    meeting = find_meeting(int(year), country.strip().title())
    if not meeting:
        st.sidebar.error(f"No meeting found for {country} {year}. Check the spelling.")
        st.stop()
    st.session_state["meeting"] = meeting
    st.session_state["sessions"] = list_sessions(meeting["meeting_key"])

if "meeting" not in st.session_state:
    st.title("🏁 F1 Race Weekend Analyzer")
    st.write("Pick a **year** and **country** in the sidebar, then click **Load weekend**.")
    st.write("Built on top of the [OpenF1 API](https://openf1.org/docs).")
    st.stop()

meeting = st.session_state["meeting"]
sessions = st.session_state["sessions"]
session_names = [s["session_name"] for s in sessions]
default_idx = session_names.index("Race") if "Race" in session_names else 0
chosen_name = st.sidebar.selectbox("Session", session_names, index=default_idx)
session = next(s for s in sessions if s["session_name"] == chosen_name)
session_key = session["session_key"]
meeting_key = meeting["meeting_key"]
is_race = session.get("session_type") == "Race"

st.title(f"{meeting['meeting_name']} — {chosen_name}")
st.caption(
    f"{meeting['circuit_short_name']}, {meeting['country_name']} "
    f"• {session['date_start'][:16].replace('T', ' ')} UTC"
)

tab_overview, tab_standings, tab_laps, tab_events, tab_radio, tab_telemetry = st.tabs(
    ["Overview", "Standings", "Laps & Stints", "Pit & Overtakes", "Race Control & Radio", "Telemetry"]
)

# ---------------------------------------------------------------------------
# Overview: meeting info, weather, driver list
# ---------------------------------------------------------------------------
with tab_overview:
    col1, col2 = st.columns([1, 2])
    with col1:
        if meeting.get("circuit_image"):
            st.image(meeting["circuit_image"], caption=meeting["circuit_short_name"])
    with col2:
        st.write(f"**{meeting['meeting_official_name']}**")
        st.write(f"📍 {meeting['location']}, {meeting['country_name']}")
        st.write(f"🏎️ {session['date_start'][:10]} → {session['date_end'][:10]}")

    st.subheader("Weather")
    weather_df = df(get_weather(meeting_key))
    if weather_df.empty:
        st.info("No weather data for this meeting.")
    else:
        weather_df["date"] = pd.to_datetime(weather_df["date"], format="ISO8601")
        fig = px.line(
            weather_df, x="date", y=["air_temperature", "track_temperature"],
            labels={"value": "°C", "date": "", "variable": ""},
        )
        st.plotly_chart(fig, use_container_width=True)
        c1, c2, c3 = st.columns(3)
        c1.metric("Humidity", f"{weather_df['humidity'].iloc[-1]}%")
        c2.metric("Wind speed", f"{weather_df['wind_speed'].iloc[-1]} m/s")
        c3.metric("Rainfall", "Yes" if weather_df["rainfall"].iloc[-1] else "No")

    st.subheader("Drivers")
    drivers_df = df(get_drivers(session_key))
    if drivers_df.empty:
        st.info("No driver data for this session.")
    else:
        st.dataframe(
            drivers_df[["driver_number", "full_name", "team_name", "name_acronym"]],
            hide_index=True,
            use_container_width=True,
        )

# ---------------------------------------------------------------------------
# Standings: starting grid, session result, championship standings
# ---------------------------------------------------------------------------
with tab_standings:
    st.subheader("Starting grid")
    grid_df = df(get_starting_grid(session_key))
    if grid_df.empty:
        st.info("No starting grid data for this session.")
    else:
        st.dataframe(grid_df.sort_values("position"), hide_index=True, use_container_width=True)

    st.subheader("Session result")
    result_df = df(get_session_result(session_key))
    if result_df.empty:
        st.info("No session result data yet — it's published a few minutes after the session ends.")
    else:
        st.dataframe(result_df.sort_values("position"), hide_index=True, use_container_width=True)

    if is_race:
        st.subheader("Championship standings (after this race)")
        cd_df = df(drivers_championship(session_key))
        ct_df = df(teams_championship(session_key))
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Drivers**")
            if cd_df.empty:
                st.info("No drivers' championship data.")
            else:
                st.dataframe(cd_df.sort_values("position_current"), hide_index=True, use_container_width=True)
        with col2:
            st.write("**Teams**")
            if ct_df.empty:
                st.info("No teams' championship data.")
            else:
                st.dataframe(ct_df.sort_values("position_current"), hide_index=True, use_container_width=True)

# ---------------------------------------------------------------------------
# Laps & Stints
# ---------------------------------------------------------------------------
with tab_laps:
    laps_df = df(get_laps(session_key))
    drivers_df = df(get_drivers(session_key))

    if laps_df.empty:
        st.info("No lap data for this session.")
    else:
        name_map = (
            dict(zip(drivers_df["driver_number"], drivers_df["name_acronym"]))
            if not drivers_df.empty else {}
        )
        laps_df["driver"] = laps_df["driver_number"].map(name_map).fillna(
            laps_df["driver_number"].astype(str)
        )
        all_drivers = sorted(laps_df["driver"].unique())
        chosen = st.multiselect("Drivers", all_drivers, default=all_drivers[:5])
        plot_df = laps_df[laps_df["driver"].isin(chosen)].sort_values("lap_number")

        st.subheader("Lap times")
        if plot_df.empty:
            st.info("Select at least one driver.")
        else:
            fig = px.line(plot_df, x="lap_number", y="lap_duration", color="driver", markers=True)
            fig.update_layout(xaxis_title="Lap", yaxis_title="Lap time (s)")
            st.plotly_chart(fig, use_container_width=True)

    st.subheader("Tyre strategy")
    stints_df = df(get_stints(session_key))
    if stints_df.empty:
        st.info("No stint data for this session.")
    else:
        fig = go.Figure()
        seen_compounds = set()
        for _, row in stints_df.sort_values("driver_number").iterrows():
            compound = row.get("compound", "UNKNOWN")
            fig.add_trace(go.Bar(
                y=[str(row["driver_number"])],
                x=[row["lap_end"] - row["lap_start"] + 1],
                base=[row["lap_start"] - 1],
                orientation="h",
                marker_color=COMPOUND_COLORS.get(compound, "#888888"),
                name=compound,
                legendgroup=compound,
                showlegend=compound not in seen_compounds,
                hovertext=f"#{row['driver_number']} — {compound}, laps {row['lap_start']}–{row['lap_end']}",
                hoverinfo="text",
            ))
            seen_compounds.add(compound)
        fig.update_layout(
            barmode="stack", xaxis_title="Lap", yaxis_title="Driver #",
            height=max(400, 25 * stints_df["driver_number"].nunique()),
        )
        st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# Pit stops & overtakes
# ---------------------------------------------------------------------------
with tab_events:
    st.subheader("Pit stops")
    pit_df = df(get_pit_stops(session_key))
    if pit_df.empty:
        st.info("No pit stop data for this session.")
    else:
        st.dataframe(pit_df.sort_values("lap_number"), hide_index=True, use_container_width=True)

    if is_race:
        st.subheader("Overtakes")
        overtakes_df = df(get_overtakes(session_key))
        if overtakes_df.empty:
            st.info("No overtake data for this session.")
        else:
            st.dataframe(overtakes_df.sort_values("date"), hide_index=True, use_container_width=True)

# ---------------------------------------------------------------------------
# Race control & team radio
# ---------------------------------------------------------------------------
with tab_radio:
    st.subheader("Race control")
    rc_df = df(get_race_control(session_key))
    if rc_df.empty:
        st.info("No race control messages for this session.")
    else:
        cols = [c for c in ["date", "category", "flag", "driver_number", "message"] if c in rc_df.columns]
        st.dataframe(rc_df[cols].sort_values("date"), hide_index=True, use_container_width=True)

    st.subheader("Team radio")
    radio_records = get_team_radio(session_key)
    if not radio_records:
        st.info("No team radio clips available for this session (F1's own coverage varies by event).")
    else:
        radio_df = df(radio_records).sort_values("date")
        drivers_df = df(get_drivers(session_key))
        name_map = (
            dict(zip(drivers_df["driver_number"], drivers_df["full_name"]))
            if not drivers_df.empty else {}
        )
        for _, row in radio_df.iterrows():
            name = name_map.get(row["driver_number"], f"#{row['driver_number']}")
            st.write(f"**{name}** — {row['date'][:19].replace('T', ' ')}")
            st.audio(row["recording_url"])

# ---------------------------------------------------------------------------
# Telemetry: car data + track location for one driver, one lap
# ---------------------------------------------------------------------------
with tab_telemetry:
    drivers_df = df(get_drivers(session_key))
    if drivers_df.empty:
        st.info("No driver data for this session.")
    else:
        drivers_df["label"] = drivers_df["full_name"] + " (#" + drivers_df["driver_number"].astype(str) + ")"
        label = st.selectbox("Driver", drivers_df["label"])
        driver_number = int(drivers_df.loc[drivers_df["label"] == label, "driver_number"].iloc[0])

        laps_df = df(get_laps(session_key, driver_number))
        if laps_df.empty:
            st.info("No lap data for this driver.")
        else:
            lap_options = sorted(laps_df["lap_number"].dropna().unique())
            lap_num = st.select_slider("Lap", options=lap_options)
            lap_row = laps_df[laps_df["lap_number"] == lap_num].iloc[0]

            date_start = pd.to_datetime(lap_row["date_start"], format="ISO8601")
            duration = lap_row.get("lap_duration") or 90
            date_end = date_start + pd.to_timedelta(float(duration), unit="s")

            date_filters = [
                f"date>={date_start.isoformat()}",
                f"date<={date_end.isoformat()}",
            ]

            car_records = raw_get(
                "car_data",
                [f"session_key={session_key}", f"driver_number={driver_number}", *date_filters],
            )
            car_df = df(car_records)

            loc_records = raw_get(
                "location",
                [f"session_key={session_key}", f"driver_number={driver_number}", *date_filters],
            )
            loc_df = df(loc_records)

            if car_df.empty:
                st.info("No car telemetry for this lap.")
            else:
                car_df["date"] = pd.to_datetime(car_df["date"], format="ISO8601")
                fig = make_subplots(
                    rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                    subplot_titles=("Speed (km/h)", "Throttle / Brake (%)", "RPM / Gear"),
                )
                fig.add_trace(go.Scatter(x=car_df["date"], y=car_df["speed"], name="Speed"), row=1, col=1)
                fig.add_trace(go.Scatter(x=car_df["date"], y=car_df["throttle"], name="Throttle"), row=2, col=1)
                fig.add_trace(go.Scatter(x=car_df["date"], y=car_df["brake"], name="Brake"), row=2, col=1)
                fig.add_trace(go.Scatter(x=car_df["date"], y=car_df["rpm"], name="RPM"), row=3, col=1)
                fig.add_trace(go.Scatter(x=car_df["date"], y=car_df["n_gear"], name="Gear"), row=3, col=1)
                fig.update_layout(height=650, showlegend=True)
                st.plotly_chart(fig, use_container_width=True)

            if loc_df.empty:
                st.info("No location data for this lap.")
            else:
                loc_df = loc_df.reset_index().rename(columns={"index": "sequence"})
                fig2 = px.scatter(
                    loc_df, x="x", y="y", color="sequence",
                    title="Track position during this lap", color_continuous_scale="Turbo",
                )
                fig2.update_yaxes(scaleanchor="x", scaleratio=1)
                fig2.update_layout(coloraxis_showscale=False)
                st.plotly_chart(fig2, use_container_width=True)
