import streamlit as st
import plotly.graph_objects as go
import random
import math
import os
from datetime import datetime
from dateutil.relativedelta import relativedelta

# ---------------------------
# 1) Tax logic (simplified)
# ---------------------------

# Base thresholds (2023-24, approximate).
# We ignore the personal allowance taper for incomes >100k, etc.
BASE_PERSONAL_ALLOWANCE = 12570
BASE_BASIC_RATE_LIMIT   = 50270  # up to this (minus PA) is 20%
BASE_HIGHER_RATE_LIMIT  = 125140 # up to this is 40%, above is 45%

def calc_tax_annual(gross, pa, brt, hrt):
    """
    Calculate total annual income tax (very simplified).
      - personal allowance 'pa' taxed at 0%,
      - income above PA to 'brt' taxed at 20%,
      - income above 'brt' to 'hrt' taxed at 40%,
      - income above 'hrt' taxed at 45%.
    """
    if gross <= 0:
        return 0

    tax = 0.0

    # 1) Personal allowance portion
    if gross <= pa:
        return 0  # all within personal allowance

    # Basic rate portion
    basic_portion = min(gross, brt) - pa
    if basic_portion < 0:
        basic_portion = 0

    # Higher rate portion
    higher_portion = 0
    if gross > brt:
        higher_portion = min(gross, hrt) - brt

    # Additional rate portion
    additional_portion = 0
    if gross > hrt:
        additional_portion = gross - hrt

    # Now compute each chunk of tax
    tax += basic_portion * 0.20
    tax += higher_portion * 0.40
    tax += additional_portion * 0.45

    return tax

def calc_net_annual(gross, pa, brt, hrt):
    """Net = gross - tax."""
    return gross - calc_tax_annual(gross, pa, brt, hrt)

def required_gross_annual_for_net_annual(net_annual, pa, brt, hrt):
    """
    Given a desired net annual income (post-tax),
    return how much gross is needed, via a binary search.
    """
    if net_annual <= 0:
        return 0

    low = 0.0
    high = 2_000_000.0  # arbitrary upper bound
    for _ in range(50):  # 50 iterations is plenty for typical use
        mid = (low + high) / 2.0
        net_mid = calc_net_annual(mid, pa, brt, hrt)
        if net_mid < net_annual:
            low = mid
        else:
            high = mid
    return high

def get_tax_brackets_for_year(year, annual_inflation_rate):
    """
    For a given 'year' (0-based) in the simulation,
    we inflate the tax thresholds every 5 years by (1+inflation)^(5 * #periods).
    E.g. for year 0-4, factor=1.0; year 5-9, factor=(1+infl)^5; etc.
    """
    # How many 5-year blocks have passed
    inflation_periods = year // 5
    factor = (1 + annual_inflation_rate) ** (5 * inflation_periods)

    pa  = BASE_PERSONAL_ALLOWANCE * factor
    brt = BASE_BASIC_RATE_LIMIT   * factor
    hrt = BASE_HIGHER_RATE_LIMIT  * factor
    return pa, brt, hrt

# ---------------------------------
# 2) Simulation logic with monthly
# ---------------------------------

def simulate_investment(
        initial_deposit,
        monthly_deposit,
        annual_return_rate,
        annual_inflation_rate,
        annual_withdrawal_rate,
        target_annual_living_cost,  # <--- This is the net annual cost you want
        years,
        annual_volatility,
        start_date
):
    """
    We interpret 'target_annual_living_cost' as the net (post-tax) cost you want each year,
    but we still do monthly inflation on it. Then we figure out how much gross is needed
    using the simplified UK tax brackets (which also adjust for inflation every 5 years).
    """
    total_months = years * 12

    # Convert annual return to monthly
    monthly_mean_return = (1 + annual_return_rate) ** (1 / 12) - 1
    monthly_std = annual_volatility / (12 ** 0.5)
    # We still do monthly inflation for the living cost
    monthly_inflation_rate = (1 + annual_inflation_rate) ** (1 / 12) - 1

    # Our "starting" monthly net cost is target_annual_living_cost/12
    initial_monthly_net_cost = target_annual_living_cost / 12.0

    portfolio_value = initial_deposit
    start_withdrawal_date = None
    withdrawing = False
    total_withdrawn = 0.0

    dates_list = []
    portfolio_values = []
    withdrawal_values = []
    monthly_net_costs = []

    for month in range(total_months):
        current_date = start_date + relativedelta(months=+month)

        # 1) Figure out how much net cost we want this month
        if month == 0:
            this_month_net_cost = initial_monthly_net_cost
        else:
            # inflate from last month
            this_month_net_cost = monthly_net_costs[-1] * (1 + monthly_inflation_rate)

        # 2) See if we can start withdrawing
        #    We'll do a rough check: if portfolio >= pre-tax cost * 12 / withdrawal rate
        #    but that was the old logic. Let's keep it simpler: We'll just start withdrawing
        #    as soon as we can. Or we can say "withdrawing = True" from day 1 if we want to
        #    replicate the old approach. Up to you. For demonstration, let's do the old check:
        #    but now we need the GROSS cost. We'll do a guess:
        #    Actually let's do: if portfolio >= 25 * annual net cost => start withdrawing
        #    but let's keep it simple. We'll do the old approach for continuity:
        required_portfolio = (this_month_net_cost * 12) / annual_withdrawal_rate
        if not withdrawing and portfolio_value >= required_portfolio:
            withdrawing = True
            start_withdrawal_date = current_date

        # 3) Add monthly deposit
        portfolio_value += monthly_deposit

        # 4) Random monthly return
        current_month_return = random.gauss(monthly_mean_return, monthly_std)
        portfolio_value *= (1 + current_month_return)

        # 5) If we're in withdrawal mode, we withdraw the GROSS amount needed to end up with net = this_month_net_cost
        if withdrawing:
            # figure out the current year
            current_year = month // 12  # 0-based
            pa, brt, hrt = get_tax_brackets_for_year(current_year, annual_inflation_rate)

            # We want this_month_net_cost * 12 net annually, so do a quick calc
            net_annual_needed = this_month_net_cost * 12
            gross_annual_needed = required_gross_annual_for_net_annual(net_annual_needed, pa, brt, hrt)
            monthly_gross_needed = gross_annual_needed / 12.0

            withdrawal_amt = min(monthly_gross_needed, portfolio_value)
            portfolio_value -= withdrawal_amt
        else:
            withdrawal_amt = 0.0

        total_withdrawn += withdrawal_amt

        # Save for later
        dates_list.append(current_date)
        portfolio_values.append(portfolio_value)
        withdrawal_values.append(withdrawal_amt)
        monthly_net_costs.append(this_month_net_cost)

    return dates_list, portfolio_values, withdrawal_values, start_withdrawal_date, total_withdrawn

# -------------------------------
# 3) Plot, summary, main app
# -------------------------------

def create_plot(dates, portfolio_values, withdrawal_values, start_withdrawal_date):
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=portfolio_values,
            mode='lines',
            line=dict(color='blue', width=2),
            name='Portfolio Value (£)'
        )
    )
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=withdrawal_values,
            mode='lines',
            line=dict(color='red', width=2, dash='dot'),
            name='Monthly Withdrawal (£)'
        )
    )
    if start_withdrawal_date is not None:
        fig.add_vline(
            x=start_withdrawal_date,
            line_width=2,
            line_color="green"
        )
        fig.add_annotation(
            x=start_withdrawal_date,
            y=1,
            xref="x",
            yref="paper",
            text="Withdrawals Begin",
            showarrow=True,
            arrowhead=1,
            ax=0,
            ay=-40
        )
    fig.update_layout(
        title="Portfolio Growth & Withdrawals Over Time (UK Tax, Brackets Inflated Every 5 Years)",
        xaxis_title="Date",
        yaxis_title="£",
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    return fig

def display_summary(start_withdrawal_date, total_withdrawn, portfolio_values, start_date):
    st.subheader("Summary")
    if start_withdrawal_date is None:
        st.write("• The portfolio never reached the threshold to sustain your target living cost (post-tax).")
        st.write(f"• Final portfolio value: £{portfolio_values[-1]:,.2f}")
        st.write("• Total withdrawn: £0.00 (No withdrawals were made.)")
    else:
        years_to_withdraw = (start_withdrawal_date - start_date).days / 365.25
        st.write(
            f"• Started withdrawing on **{start_withdrawal_date.strftime('%Y-%m-%d')}** "
            f"(after about **{years_to_withdraw:.2f} years**)."
        )
        st.write(f"• Final portfolio value: £{portfolio_values[-1]:,.2f}")
        st.write(f"• Total withdrawn: £{total_withdrawn:,.2f}")

def run_monte_carlo(
    initial_deposit,
    monthly_deposit,
    annual_return_rate,
    annual_inflation_rate,
    annual_withdrawal_rate,
    target_annual_living_cost,
    years,
    annual_volatility,
    start_date,
    num_simulations
):
    """
    We'll define 'success' the same way as before:
    - The simulation must start withdrawals at some point (start_withdrawal_date != None)
    - And end with a positive portfolio value
    """
    success_count = 0
    for _ in range(num_simulations):
        _, portfolio_values, _, start_withdrawal_date, _ = simulate_investment(
            initial_deposit,
            monthly_deposit,
            annual_return_rate,
            annual_inflation_rate,
            annual_withdrawal_rate,
            target_annual_living_cost,
            years,
            annual_volatility,
            start_date
        )
        if start_withdrawal_date is not None and portfolio_values[-1] > 0:
            success_count += 1
    return (success_count / num_simulations) * 100

def main():
    st.title("Haris' Lods of Emone Simulator (with Simplified UK Taxes)")
    st.write(
        "A rough demonstration of how UK income tax might reduce your net withdrawals, "
        "with tax brackets inflated every 5 years. Not actual tax advice!"
    )
    st.info("On mobile, tap the menu in the top-left corner to see the Simulation Parameters.")

    st.sidebar.header("Simulation Parameters")
    start_date = st.sidebar.date_input("Starting Date", value=datetime.today())
    initial_deposit = st.sidebar.number_input("Initial Deposit (£)", min_value=0, value=1000, step=500)
    monthly_deposit = st.sidebar.number_input("Monthly Deposit (£)", min_value=0, value=100, step=50)
    annual_return_rate = st.sidebar.slider("Annual Return Rate (%)", 0.0, 20.0, 14.8, 0.2) / 100.0
    annual_inflation_rate = st.sidebar.slider("Annual Inflation Rate (%)", 0.0, 7.0, 4.8, 0.2) / 100.0
    annual_withdrawal_rate = st.sidebar.slider("Annual Withdrawal Rate (%)", 0.0, 20.0, 4.0, 0.5) / 100.0

    st.sidebar.markdown("**Target Net Annual Living Cost**")
    target_annual_living_cost = st.sidebar.number_input(
        "Amount you want to spend per year (post-tax, £)",
        min_value=0,
        value=30000,
        step=1000
    )

    years = st.sidebar.slider("Number of Years to Simulate", 1, 100, 20, 1)
    annual_volatility = st.sidebar.slider("Annual Volatility (%)", 0.0, 50.0, 15.0, 0.5) / 100.0
    num_simulations = st.sidebar.number_input("Monte Carlo Simulations", min_value=100, value=1000, step=100)

    # 1) Run single simulation
    dates, portfolio_values, withdrawal_values, start_withdrawal_date, total_withdrawn = simulate_investment(
        initial_deposit,
        monthly_deposit,
        annual_return_rate,
        annual_inflation_rate,
        annual_withdrawal_rate,
        target_annual_living_cost,  # net cost
        years,
        annual_volatility,
        start_date
    )
    fig = create_plot(dates, portfolio_values, withdrawal_values, start_withdrawal_date)
    st.plotly_chart(fig, use_container_width=True)
    display_summary(start_withdrawal_date, total_withdrawn, portfolio_values, start_date)

    # 2) Monte Carlo success probability
    st.subheader("Monte Carlo Success Probability")
    probability = run_monte_carlo(
        initial_deposit,
        monthly_deposit,
        annual_return_rate,
        annual_inflation_rate,
        annual_withdrawal_rate,
        target_annual_living_cost,
        years,
        annual_volatility,
        start_date,
        int(num_simulations)
    )
    st.write(
        f"Based on {num_simulations} simulations, the probability of achieving your post-tax living cost "
        f"and still ending with a positive portfolio is **{probability:.2f}%**."
    )

if __name__ == "__main__":
    main()
