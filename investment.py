import streamlit as st
import plotly.graph_objects as go
import random
import math
import os
from datetime import datetime
from dateutil.relativedelta import relativedelta
import statistics

########################
# 1) TAX & UTILITY FUNCS
########################
BASE_PERSONAL_ALLOWANCE = 12570
BASE_BASIC_RATE_LIMIT = 50270
BASE_HIGHER_RATE_LIMIT = 125140

def calc_tax_annual(gross, pa, brt, hrt):
    """Simple tiered UK tax calculation for a single year's withdrawal."""
    if gross <= 0:
        return 0.0
    if gross <= pa:
        return 0.0
    tax = 0.0
    basic_portion = max(0, min(gross, brt) - pa)
    higher_portion = max(0, min(gross, hrt) - brt) if gross > brt else 0
    additional_portion = max(0, gross - hrt) if gross > hrt else 0

    tax += basic_portion * 0.20
    tax += higher_portion * 0.40
    tax += additional_portion * 0.45
    return tax

def calc_net_annual(gross, pa, brt, hrt):
    """Net after tax for a single year's withdrawal."""
    return gross - calc_tax_annual(gross, pa, brt, hrt)

def required_gross_annual_for_net_annual(net_annual, pa, brt, hrt):
    """
    How much gross do we need so that net is 'net_annual'?
    Binary search, to handle tax tiers.
    """
    if net_annual <= 0:
        return 0.0
    low, high = 0.0, 2_000_000.0
    for _ in range(50):
        mid = (low + high) / 2.0
        net = calc_net_annual(mid, pa, brt, hrt)
        if net < net_annual:
            low = mid
        else:
            high = mid
    return high

def get_tax_brackets_for_factor(factor):
    """Inflate bracket cutoffs by 'factor' for the year."""
    pa = BASE_PERSONAL_ALLOWANCE * factor
    brt = BASE_BASIC_RATE_LIMIT * factor
    hrt = BASE_HIGHER_RATE_LIMIT * factor
    return pa, brt, hrt

#############################
# 2) SIMULATE NO WITHDRAWALS
#############################
def simulate_no_withdrawals_annual(
    initial_deposit,
    annual_deposit,
    deposit_growth_rate,
    annual_return_rate,
    years,
    annual_volatility,
    start_date,
    num_simulations
):
    """
    Run many simulations WITHOUT retirement/withdrawals,
    and then we'll average them to get a single "average portfolio path."
    """
    dates = [start_date + relativedelta(years=yr) for yr in range(years)]
    all_portfolios = []

    for _ in range(num_simulations):
        portfolio_values = []
        portfolio = float(initial_deposit)
        current_annual_deposit = float(annual_deposit)

        for yr in range(years):
            # 1) deposit
            portfolio += current_annual_deposit
            # deposit grows for next year
            current_annual_deposit *= (1 + deposit_growth_rate)

            # 2) random annual return
            annual_return = random.gauss(annual_return_rate, annual_volatility)
            portfolio *= (1 + annual_return)

            portfolio_values.append(portfolio)

        all_portfolios.append(portfolio_values)

    # Now average them across runs for each year
    avg_portfolio_per_year = []
    for year_index in range(years):
        year_vals = [all_portfolios[sim][year_index] for sim in range(num_simulations)]
        avg_portfolio_per_year.append(sum(year_vals) / num_simulations)

    return dates, avg_portfolio_per_year

######################################
# 3) APPLY WITHDRAWALS TO ONE AVG RUN
######################################
def apply_withdrawal_logic_to_avg_portfolio(
    dates,
    avg_portfolio_values,
    annual_inflation_rate,
    annual_withdrawal_rate,
    target_annual_living_cost,
    mode="strict"
):
    """
    We take a single portfolio path (the average), and run the retirement logic ONCE.
    """
    from copy import deepcopy
    portfolio_values = deepcopy(avg_portfolio_values)

    tax_factor = 1.0
    current_annual_cost = float(target_annual_living_cost)

    withdrawing = False
    start_withdrawal_date = None
    total_withdrawn = 0.0
    withdrawal_values = []

    for i, date in enumerate(dates):
        pa, brt, hrt = get_tax_brackets_for_factor(tax_factor)

        # Check if 4% of this year's portfolio can cover cost
        net_if_4_percent = calc_net_annual(annual_withdrawal_rate * portfolio_values[i], pa, brt, hrt)

        # Decide if we can retire this year
        if (not withdrawing) and (net_if_4_percent >= current_annual_cost):
            withdrawing = True
            start_withdrawal_date = date

        # If retired, do withdrawal
        if withdrawing:
            if mode == "strict":
                needed_gross = required_gross_annual_for_net_annual(current_annual_cost, pa, brt, hrt)
                if portfolio_values[i] >= needed_gross:
                    wd_amt = needed_gross
                else:
                    wd_amt = max(0, portfolio_values[i])
            else:  # four_percent
                wd_amt = annual_withdrawal_rate * portfolio_values[i]
                if portfolio_values[i] < wd_amt:
                    wd_amt = max(0, portfolio_values[i])

            portfolio_values[i] -= wd_amt
        else:
            wd_amt = 0.0

        withdrawal_values.append(wd_amt)
        total_withdrawn += wd_amt

        # For next year, inflation
        tax_factor *= (1 + annual_inflation_rate)
        current_annual_cost *= (1 + annual_inflation_rate)

    return portfolio_values, withdrawal_values, start_withdrawal_date, total_withdrawn

##########################
# 4) STREAMLIT MAIN APP
##########################
def main():
    st.set_page_config(page_title="Two-Step Average Withdrawal Sim", layout="wide")

    st.title("Two-Step Annual Simulation: Average Growth, Then Withdrawals")
    st.write(
        "1) We first simulate many runs of deposit + returns (no retirement at all) and average them. \n"
        "2) We then apply retirement logic ONCE to that single average portfolio path.\n\n"
        "Hence, no more 'skewed' withdrawal lines from runs that never retire!"
    )

    # === Default parameter dictionary (ANNUAL) ===
    default_params = {
        "start_date": datetime.today().date(),
        "initial_deposit": 10000,
        "annual_deposit": 6000,  # e.g. 500 per month x 12
        "annual_inflation_rate": 3.0,    # 3% annual
        "deposit_growth_rate": 2.0,      # 2% annual deposit growth
        "annual_return_rate": 7.0,       # 7% annual
        "annual_withdrawal_rate": 4.0,   # 4% rule
        "target_annual_living_cost": 30000,
        "years": 40,
        "annual_volatility": 10.0,       # 10% stdev
        "num_simulations": 50
    }

    # === SIDEBAR FOR INPUT ===
    st.sidebar.header("Simulation Parameters (No Withdrawals Phase)")
    user_start_date = st.sidebar.date_input(
        "Starting Date",
        value=default_params["start_date"]
    )
    user_initial_deposit = st.sidebar.number_input(
        "Initial Deposit (£)",
        min_value=0,
        value=default_params["initial_deposit"],
        step=1000
    )
    user_annual_deposit = st.sidebar.number_input(
        "Annual Deposit (£)",
        min_value=0,
        value=default_params["annual_deposit"],
        step=1000
    )
    user_annual_inflation_rate = st.sidebar.slider(
        "Annual Inflation Rate (%)",
        0.0, 10.0,
        default_params["annual_inflation_rate"], 0.1
    )
    user_deposit_growth_rate = st.sidebar.slider(
        "Annual Deposit Growth Rate (%)",
        0.0, 10.0,
        default_params["deposit_growth_rate"], 0.1
    )
    user_annual_return_rate = st.sidebar.slider(
        "Annual Return Rate (%)",
        0.0, 20.0,
        default_params["annual_return_rate"], 0.1
    )
    user_annual_volatility = st.sidebar.slider(
        "Annual Volatility (%)",
        0.0, 50.0,
        default_params["annual_volatility"], 0.1
    )
    user_years = st.sidebar.slider(
        "Number of Years to Simulate",
        1, 60,
        default_params["years"]
    )
    user_num_sims = st.sidebar.number_input(
        "Monte Carlo Simulations (No-Withdrawal Phase)",
        min_value=1,
        value=default_params["num_simulations"],
        step=1
    )

    # === WITHDRAWAL PHASE ===
    st.sidebar.header("Withdrawal Logic (Applied to Avg Path)")
    user_annual_withdrawal_rate = st.sidebar.slider(
        "Annual Withdrawal Rate (%)",
        0.0, 20.0,
        default_params["annual_withdrawal_rate"], 0.1
    )
    user_target_annual_living_cost = st.sidebar.number_input(
        "Target Net Annual Living Cost (£)",
        min_value=0,
        value=default_params["target_annual_living_cost"],
        step=1000
    )
    user_mode = st.sidebar.selectbox(
        "Withdrawal Mode",
        ("strict", "four_percent"),
        index=0
    )

    # Convert percentages => decimals
    user_annual_inflation_rate /= 100.0
    user_deposit_growth_rate /= 100.0
    user_annual_return_rate /= 100.0
    user_annual_withdrawal_rate /= 100.0
    user_annual_volatility /= 100.0

    # === STEP 1: SIMULATE & AVERAGE (NO WITHDRAWALS) ===
    st.subheader("Step 1: Generate an Average Portfolio Path (No Retirement Logic)")
    dates, avg_portfolio_values = simulate_no_withdrawals_annual(
        initial_deposit=user_initial_deposit,
        annual_deposit=user_annual_deposit,
        deposit_growth_rate=user_deposit_growth_rate,
        annual_return_rate=user_annual_return_rate,
        years=user_years,
        annual_volatility=user_annual_volatility,
        start_date=user_start_date,
        num_simulations=user_num_sims
    )

    # === STEP 2: APPLY WITHDRAWAL LOGIC ONCE TO THE AVERAGE PATH ===
    st.subheader("Step 2: Apply Withdrawal Logic to That Single Average Path")
    final_pf_values, wd_values, wd_start, total_wd = apply_withdrawal_logic_to_avg_portfolio(
        dates=dates,
        avg_portfolio_values=avg_portfolio_values,
        annual_inflation_rate=user_annual_inflation_rate,
        annual_withdrawal_rate=user_annual_withdrawal_rate,
        target_annual_living_cost=user_target_annual_living_cost,
        mode=user_mode
    )

    # === PLOT THE RESULTS ===
    fig = go.Figure()

    # Plot the "pre-withdrawal" average portfolio
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=avg_portfolio_values,
            name="Avg Portfolio (No Withdrawals)",
            mode='lines+markers',
            line=dict(color='skyblue', width=2)
        )
    )

    # Plot the "post-withdrawal" final portfolio
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=final_pf_values,
            name="Portfolio After Withdrawals",
            mode='lines+markers',
            line=dict(color='orange', width=3)
        )
    )

    # Plot the yearly withdrawals
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=wd_values,
            name="Yearly Withdrawals",
            mode='lines+markers',
            line=dict(color='magenta', width=2, dash='dot')
        )
    )

    # Mark the start of withdrawals
    if wd_start:
        idx_wd = dates.index(wd_start)
        fig.add_vline(x=wd_start, line_width=2, line_dash="dash", line_color="green")
        fig.add_annotation(
            x=wd_start,
            y=final_pf_values[idx_wd],
            text="Withdrawal Start",
            showarrow=True,
            arrowhead=2,
            ax=0,
            ay=-40,
            font=dict(color="green"),
            arrowcolor="green"
        )

    fig.update_layout(
        title="2-Step Simulation: Average Growth, Then Withdrawals",
        xaxis_title="Year",
        yaxis_title="Portfolio Value (£)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    st.plotly_chart(fig, use_container_width=True)

    # === SUMMARY ===
    st.subheader("Summary")
    if wd_start:
        years_into_sim = (wd_start - dates[0]).days / 365.25
        st.write(f"• Retirement began on {wd_start.strftime('%Y-%m-%d')} (~{years_into_sim:.2f} years in).")
    else:
        st.write("• We never hit the 4% threshold on the average path; no retirement triggered.")
    st.write(f"• Total withdrawn (avg scenario): £{total_wd:,.2f}")
    st.write(f"• Final portfolio value (avg scenario): £{final_pf_values[-1]:,.2f}")

    # Simple inflation check
    infl_factor = (1 + user_annual_inflation_rate) ** user_years
    st.write(
        f"**Inflation Check:** With {user_annual_inflation_rate * 100:.2f}% annual inflation over {user_years} years, "
        f"£100 today is about £{100 * infl_factor:,.2f} in year {user_years}."
    )

if __name__ == "__main__":
    main()