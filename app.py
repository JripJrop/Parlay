import math
import random
from dataclasses import dataclass
from typing import List

import pandas as pd
import streamlit as st


# -------- Data structures -------- #

@dataclass
class Leg:
    name: str
    odds_decimal: float
    confidence: float  # 0.0–1.0
    current_count: int = 0
    target_exposure: float = 0.5  # fraction of parlays we want it in


@dataclass
class Parlay:
    legs: List[Leg]
    stake: float

    @property
    def combined_odds(self) -> float:
        prod = 1.0
        for leg in self.legs:
            prod *= leg.odds_decimal
        return prod

    @property
    def potential_win(self) -> float:
        return self.stake * self.combined_odds


# -------- Helper functions -------- #

def american_to_decimal(odds_american: float) -> float:
    if odds_american > 0:
        return 1 + odds_american / 100.0
    else:
        return 1 + 100.0 / abs(odds_american)


def set_target_exposures(
    legs: List[Leg],
    base_exposure: float = 0.5,
    slope: float = 0.4,
    min_exp: float = 0.2,
    max_exp: float = 0.9,
):
    """
    base_exposure: baseline exposure fraction
    slope: how much confidence moves exposure
    """
    for leg in legs:
        target = base_exposure + (leg.confidence - 0.5) * slope
        target = max(min_exp, min(max_exp, target))
        leg.target_exposure = target
        leg.current_count = 0  # reset


def build_parlays(
    legs: List[Leg],
    num_parlays: int = 200,
    min_legs: int = 5,
    max_legs: int = 11,
    min_combined_odds: float = 15.0,
    stake_per_parlay: float = 1.0,
    max_exposure_cap: float = 0.9,
    rng_seed: int | None = None,
) -> List[Parlay]:
    if rng_seed is not None:
        random.seed(rng_seed)

    parlays: List[Parlay] = []

    def current_exposure(leg: Leg) -> float:
        if len(parlays) == 0:
            return 0.0
        return leg.current_count / len(parlays)

    for _ in range(num_parlays):
        # Choose parlay size
        size = random.randint(min_legs, max_legs)

        # Build a pool of eligible legs (those not over hard cap)
        eligible_legs = [leg for leg in legs if current_exposure(leg) < max_exposure_cap]
        if len(eligible_legs) < min_legs:
            break

        selected = set()
        attempts = 0

        while len(selected) < size and attempts < 500:
            attempts += 1

            weights = []
            candidates = []

            for leg in eligible_legs:
                if leg in selected:
                    continue
                gap = max(0.0, leg.target_exposure - current_exposure(leg))
                base_weight = 0.05 + gap * 1.0
                weight = base_weight * (0.5 + leg.confidence)
                weights.append(weight)
                candidates.append(leg)

            if not candidates:
                break

            chosen = random.choices(candidates, weights=weights, k=1)[0]
            selected.add(chosen)

        parlay_legs = list(selected)

        if len(parlay_legs) < min_legs:
            continue

        # Ensure minimum combined odds by optionally adding more legs
        boost_attempts = 0
        while True:
            combined = 1.0
            for leg in parlay_legs:
                combined *= leg.odds_decimal

            if combined >= min_combined_odds or len(parlay_legs) >= max_legs:
                break

            remaining = [
                l
                for l in legs
                if l not in parlay_legs and current_exposure(l) < max_exposure_cap
            ]
            if not remaining:
                break
            parlay_legs.append(random.choice(remaining))
            boost_attempts += 1
            if boost_attempts > 50:
                break

        if len(parlay_legs) < min_legs:
            continue

        combined_odds = 1.0
        for leg in parlay_legs:
            combined_odds *= leg.odds_decimal
        if combined_odds < min_combined_odds:
            continue

        p = Parlay(legs=parlay_legs, stake=stake_per_parlay)
        parlays.append(p)

        for leg in parlay_legs:
            leg.current_count += 1

    return parlays


# -------- Streamlit UI -------- #

def main():
    st.set_page_config(page_title="Parlay Portfolio Builder", layout="wide")

    st.title("Parlay Portfolio Builder (5–11 Legs)")
    st.caption("Generate many small longshot parlays with controlled leg exposure.")

    # Sidebar controls
    with st.sidebar:
        st.header("Global Settings")

        num_parlays = st.number_input(
            "Number of parlays to generate",
            min_value=1,
            max_value=2000,
            value=200,
            step=10,
        )

        min_legs = st.number_input(
            "Minimum legs per parlay",
            min_value=2,
            max_value=20,
            value=5,
        )
        max_legs = st.number_input(
            "Maximum legs per parlay",
            min_value=min_legs,
            max_value=30,
            value=11,
        )

        min_combined_odds = st.number_input(
            "Minimum combined odds (decimal)",
            min_value=1.0,
            max_value=10000.0,
            value=20.0,
            step=1.0,
        )

        stake_per_parlay = st.number_input(
            "Stake per parlay ($)",
            min_value=0.1,
            max_value=1000.0,
            value=1.0,
            step=0.5,
        )

        st.subheader("Exposure Settings")
        base_exposure = st.slider(
            "Base target exposure per leg",
            min_value=0.1,
            max_value=0.9,
            value=0.5,
            step=0.05,
        )
        exposure_slope = st.slider(
            "Exposure sensitivity to confidence",
            min_value=0.0,
            max_value=1.0,
            value=0.4,
            step=0.05,
        )
        min_exp = st.slider(
            "Min target exposure",
            min_value=0.0,
            max_value=1.0,
            value=0.25,
            step=0.05,
        )
        max_exp = st.slider(
            "Max target exposure",
            min_value=0.0,
            max_value=1.0,
            value=0.9,
            step=0.05,
        )
        max_exposure_cap = st.slider(
            "Hard cap exposure per leg",
            min_value=0.1,
            max_value=1.0,
            value=0.9,
            step=0.05,
        )

        st.subheader("Randomness")
        rng_seed = st.number_input(
            "Random seed (optional, for reproducible results)",
            min_value=0,
            max_value=10_000_000,
            value=0,
            step=1,
        )
        use_seed = st.checkbox("Use random seed", value=False)

    st.markdown("### Step 1: Enter your legs")

    odds_mode = st.radio(
        "Odds format for input",
        options=["American", "Decimal"],
        index=0,
        horizontal=True,
    )

    default_data = pd.DataFrame(
        [
            {"Name": "Lions ML", "Odds": 120, "Confidence (0–100)": 80},
            {"Name": "Over 47.5", "Odds": -110, "Confidence (0–100)": 75},
            {"Name": "St Brown TD", "Odds": 135, "Confidence (0–100)": 70},
            {"Name": "Goff 250+ yards", "Odds": 105, "Confidence (0–100)": 72},
        ]
    )

    legs_df = st.data_editor(
        default_data,
        num_rows="dynamic",
        use_container_width=True,
        key="legs_editor",
        column_config={
            "Name": st.column_config.TextColumn("Leg name"),
            "Odds": st.column_config.NumberColumn(
                f"Odds ({odds_mode})",
                step=1,
                format="%d" if odds_mode == "American" else "%.2f",
            ),
            "Confidence (0–100)": st.column_config.NumberColumn(
                "Confidence (0–100)", min_value=0, max_value=100, step=1
            ),
        },
    )

    st.markdown("### Step 2: Generate parlays")

    generate = st.button("Generate Parlay Portfolio", type="primary")

    if generate:
        # Clean and validate leg input
        cleaned_rows = []
        for _, row in legs_df.iterrows():
            name = str(row.get("Name", "")).strip()
            odds_val = row.get("Odds", None)
            conf_val = row.get("Confidence (0–100)", 50)

            if not name:
                continue
            if odds_val is None or (isinstance(odds_val, float) and math.isnan(odds_val)):
                continue

            try:
                odds_val = float(odds_val)
            except Exception:
                continue

            confidence = max(0.0, min(1.0, float(conf_val) / 100.0))

            if odds_mode == "American":
                odds_decimal = american_to_decimal(odds_val)
            else:
                odds_decimal = float(odds_val)
                if odds_decimal <= 1.0:
                    continue

            cleaned_rows.append(
                Leg(
                    name=name,
                    odds_decimal=odds_decimal,
                    confidence=confidence,
                )
            )

        if len(cleaned_rows) < min_legs:
            st.error(f"You need at least {min_legs} valid legs to build parlays.")
            return

        legs_list: List[Leg] = cleaned_rows

        # Set exposure targets
        set_target_exposures(
            legs_list,
            base_exposure=base_exposure,
            slope=exposure_slope,
            min_exp=min_exp,
            max_exp=max_exp,
        )

        seed_val = int(rng_seed) if use_seed else None

        parlays = build_parlays(
            legs=legs_list,
            num_parlays=int(num_parlays),
            min_legs=int(min_legs),
            max_legs=int(max_legs),
            min_combined_odds=float(min_combined_odds),
            stake_per_parlay=float(stake_per_parlay),
            max_exposure_cap=float(max_exposure_cap),
            rng_seed=seed_val,
        )

        if not parlays:
            st.error(
                "No parlays could be generated with the current settings. "
                "Try lowering the minimum combined odds or relaxing exposure caps."
            )
            return

        st.success(f"Generated {len(parlays)} parlays.")

        # Summary metrics
        total_stake = sum(p.stake for p in parlays)
        avg_combined_odds = sum(p.combined_odds for p in parlays) / len(parlays)
        max_combined_odds = max(p.combined_odds for p in parlays)
        min_combined_odds_real = min(p.combined_odds for p in parlays)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total parlays", len(parlays))
        col2.metric("Total stake ($)", f"{total_stake:,.2f}")
        col3.metric("Avg combined odds (x)", f"{avg_combined_odds:,.1f}")
        col4.metric(
            "Range of odds (x)",
            f"{min_combined_odds_real:,.1f} – {max_combined_odds:,.1f}",
        )

        # Parlays table
        parlay_rows = []
        for idx, p in enumerate(parlays, start=1):
            parlay_rows.append(
                {
                    "Parlay #": idx,
                    "Legs": ", ".join(leg.name for leg in p.legs),
                    "# Legs": len(p.legs),
                    "Combined Odds (x)": round(p.combined_odds, 2),
                    "Stake ($)": round(p.stake, 2),
                    "Potential Win ($)": round(p.potential_win, 2),
                }
            )

        parlays_df = pd.DataFrame(parlay_rows)
        st.markdown("#### Generated Parlays")
        st.dataframe(parlays_df, use_container_width=True)

        # Exposure report
        exposure_rows = []
        for leg in legs_list:
            exposure = leg.current_count / len(parlays)
            exposure_rows.append(
                {
                    "Leg name": leg.name,
                    "Tickets containing leg": leg.current_count,
                    "Exposure (%)": round(exposure * 100, 1),
                    "Target exposure (%)": round(leg.target_exposure * 100, 1),
                    "Decimal odds": round(leg.odds_decimal, 3),
                }
            )
        exposure_df = pd.DataFrame(exposure_rows).sort_values(
            "Exposure (%)", ascending=False
        )

        st.markdown("#### Leg Exposure")
        st.dataframe(exposure_df, use_container_width=True)

        st.caption(
            "Tip: If exposure is hitting the hard cap often, either add more legs, "
            "reduce the number of parlays, or adjust exposure settings."
        )


if __name__ == "__main__":
    main()
