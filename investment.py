import streamlit as st
import plotly.graph_objects as go
import random
import math
import os
from datetime import datetime
from dateutil.relativedelta import relativedelta

# ---------------------------
# 1) Tax Logic (Simplified)
# ---------------------------

# Base thresholds (2023-24, approximate)
BASE_PERSONAL_ALLOWANCE = 12570
BASE_BASIC_RATE_LIMIT = 50270  # up to this (minus PA) taxed at 20%
BASE_HIGHER_RATE_LIMIT = 125140  # up to this taxed at 40%, above taxed at 45%


def calc_tax_annual(gross, pa, brt, hrt):
    """Calculate total annual income tax using simplified UK brackets."""
    if gross <= 0:
        return 0.0
    tax = 0.0
    if gross <= pa:
        return 0.0
    basic_portion = max(0, min(gross, brt) - pa)
    higher_portion = 0
    if gross > brt:
        higher_portion = min(gross, hrt) - brt
    additional_portion = 0
    if gross > hrt:
        additional_portion = gross - hrt
    tax += basic_portion * 0.20
    tax += higher_portion * 0.40
    tax += additional_portion * 0.45
    return tax


def calc_net_annual(gross, pa, brt, hrt):
    """Return net annual income given a gross amount."""
    return gross - calc_tax_annual(gross, pa, brt, hrt)


def required_gross_annual_for_net_annual(net_annual, pa, brt, hrt):
    """Using binary search, find the gross needed to yield the desired net."""
    if net_annual <= 0:
        return 0.0
    low, high = 0.0, 2_000_000.0
    for _ in range(50):
        mid = (low + high) / 2.0
        if calc_net_annual(mid, pa, brt, hrt) < net_annual:
            low = mid
        else:
            high = mid
    return high


def get_tax_brackets_for_year(year, annual_inflation_rate):
    """
    For a given simulation year (0-based), adjust the base thresholds every 5 years.
    For years 0-4, factor = 1.0; for 5-9, factor = (1+inflation)^5; etc.
    """
    inflation_periods = year // 5
    factor = (1 + annual_inflation_rate) ** (5 * inflation_periods)
    pa = BASE_PERSONAL_ALLOWANCE * factor
    brt = BASE_BASIC_RATE_LIMIT * factor
    hrt = BASE_HIGHER_RATE_LIMIT * factor
    return pa, brt, hrt


# ----------------------------------
# 2) Simulation Logic (Monthly)
# ----------------------------------

def simulate_investment(
        initial_deposit,
        monthly_deposit,
        deposit_growth_rate,  # New: monthly deposit increases at this rate each month
        annual_return_rate,
        annual_inflation_rate,
        annual_withdrawal_rate,
        target_annual_living_cost,  # desired net (post-tax) annual cost
        years,
        annual_volatility,
        start_date
):
    """
    Simulate a portfolio that aims to cover a target net living cost.

    - Living cost (net) is inflated monthly.
    - We convert the net cost to a required gross withdrawal using the current year's tax brackets.
    - Withdrawals begin once the portfolio can sustain that gross withdrawal.
    - Monthly deposits grow each month at a rate that is capped to be no higher than inflation.
    """
    total_months = years * 12

    # Convert annual return and inflation to monthly rates.
    monthly_mean_return = (1 + annual_return_rate) ** (1 / 12) - 1
    monthly_std = annual_volatility / (12 ** 0.5)
    monthly_inflation_rate = (1 + annual_inflation_rate) ** (1 / 12) - 1

    # Starting net monthly cost (desired net living cost divided by 12)
    initial_monthly_net_cost = target_annual_living_cost / 12.0

    portfolio_value = initial_deposit
    start_withdrawal_date = None
    withdrawing = False
    total_withdrawn = 0.0

    dates_list = []
    portfolio_values = []
    withdrawal_values = []
    monthly_net_costs = []

    # Set up the current monthly deposit amount that will grow over time.
    current_monthly_deposit = monthly_deposit

    for month in range(total_months):
        current_date = start_date + relativedelta(months=+month)

        # Update net living cost with monthly inflation.
        if month == 0:
            this_month_net_cost = initial_monthly_net_cost
        else:
            this_month_net_cost = monthly_net_costs[-1] * (1 + monthly_inflation_rate)

        # Determine required portfolio to start withdrawals (using pre-tax cost).
        required_portfolio = (this_month_net_cost * 12) / annual_withdrawal_rate
        if not withdrawing and portfolio_value >= required_portfolio:
            withdrawing = True
            start_withdrawal_date = current_date

        # Increase the monthly deposit by deposit_growth_rate (capped to inflation)
        if month > 0:
            current_monthly_deposit *= (1 + deposit_growth_rate)
        # Add the current monthly deposit to the portfolio.
        portfolio_value += current_monthly_deposit

        # Apply random monthly return.
        current_month_return = random.gauss(monthly_mean_return, monthly_std)
        portfolio_value *= (1 + current_month_return)

        # If in withdrawal mode, calculate required gross withdrawal:
        if withdrawing:
            current_year = month // 12  # 0-based year
            pa, brt, hrt = get_tax_brackets_for_year(current_year, annual_inflation_rate)
            net_annual_needed = this_month_net_cost * 12
            gross_annual_needed = required_gross_annual_for_net_annual(net_annual_needed, pa, brt, hrt)
            monthly_gross_needed = gross_annual_needed / 12.0
            withdrawal_amt = min(monthly_gross_needed, portfolio_value)
            portfolio_value -= withdrawal_amt
        else:
            withdrawal_amt = 0.0

        total_withdrawn += withdrawal_amt

        dates_list.append(current_date)
        portfolio_values.append(portfolio_value)
        withdrawal_values.append(withdrawal_amt)
        monthly_net_costs.append(this_month_net_cost)

    return dates_list, portfolio_values, withdrawal_values, start_withdrawal_date, total_withdrawn


# -------------------------------
# 3) Plotting & Summary Functions
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
        fig.add_vline(x=start_withdrawal_date, line_width=2, line_color="green")
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
        title="Portfolio Growth & Withdrawals Over Time (UK Tax with 5-Year Inflation Adjustment)",
        xaxis_title="Date",
        yaxis_title="£",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
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


# -------------------------------
# 4) Monte Carlo & Meme Functions
# -------------------------------

def run_monte_carlo(
        initial_deposit,
        monthly_deposit,
        deposit_growth_rate,
        annual_return_rate,
        annual_inflation_rate,
        annual_withdrawal_rate,
        target_annual_living_cost,
        years,
        annual_volatility,
        start_date,
        num_simulations
):
    success_count = 0
    for _ in range(num_simulations):
        _, portfolio_values, _, start_withdrawal_date, _ = simulate_investment(
            initial_deposit,
            monthly_deposit,
            deposit_growth_rate,
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


def display_memes(probability):
    """
    Display exactly ONE meme, centered, based on whether the outcome is 'good' or 'bad'.
    We'll say 'good' if probability >= 50, else 'bad'.
    """
    good_memes_folder = "goodMemes"
    bad_memes_folder = "badMemes"

    if probability >= 80:
        meme_folder = good_memes_folder
        st.markdown("### Congratulations! It's a Good Outcome Meme Break")
    else:
        meme_folder = bad_memes_folder
        st.markdown("### Ouch... It's a Bad Outcome Meme Break")

    try:
        all_files = os.listdir(meme_folder)
        image_files = [f for f in all_files if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))]
        if not image_files:
            st.write("No meme images found in", meme_folder)
            return
        chosen_meme = random.choice(image_files)
        meme_path = os.path.join(meme_folder, chosen_meme)
        col1, col2, col3 = st.columns([1, 2, 1])
        col2.image(meme_path, caption=chosen_meme, width=300)
    except Exception as e:
        st.write("Could not load memes from folder:", meme_folder)
        st.write(e)


# -------------------------------
# 5) Main App
# -------------------------------

def main():
    st.title("Haris' Lods of Emone Simulator (with UK Taxes & Growing Deposits)")
    st.write(
        "This simulator treats your target living cost as **post-tax** using a simplified UK tax model with "
        "brackets adjusted for inflation every 5 years. Monthly deposits also increase over time (capped at the inflation rate)."
    )
    st.info("On mobile, tap the menu in the top-left corner to see the Simulation Parameters.")

    # Sidebar inputs
    st.sidebar.header("Simulation Parameters")
    start_date = st.sidebar.date_input("Starting Date", value=datetime.today())
    initial_deposit = st.sidebar.number_input("Initial Deposit (£)", min_value=0, value=1000, step=500)
    monthly_deposit = st.sidebar.number_input("Monthly Deposit (£)", min_value=0, value=100, step=50)
    # New: Monthly deposit growth rate slider.
    # It cannot exceed the inflation rate.
    annual_inflation_rate = st.sidebar.slider("Annual Inflation Rate (%)", 0.0, 7.0, 4.8, 0.2) / 100.0
    deposit_growth_rate = st.sidebar.slider(
        "Monthly Deposit Growth Rate (%)",
        0.0, annual_inflation_rate * 100, annual_inflation_rate * 30, 0.1
    ) / 100.0
    annual_return_rate = st.sidebar.slider("Annual Return Rate (%)", 0.0, 20.0, 14.8, 0.2) / 100.0
    annual_withdrawal_rate = st.sidebar.slider("Annual Withdrawal Rate (%)", 0.0, 20.0, 4.0, 0.5) / 100.0

    st.sidebar.markdown("**Target Net Annual Living Cost**")
    target_annual_living_cost = st.sidebar.number_input(
        "Amount you want to spend per year (post-tax, £)",
        min_value=0,
        value=30000,
        step=1000
    )
    years = st.sidebar.slider("Number of Years to Simulate", 1, 100, 20, 1)
    annual_volatility = st.sidebar.slider("Annual Volatility (%)", 0.0, 30.0, 15.0, 0.2) / 100.0
    num_simulations = st.sidebar.number_input("Monte Carlo Simulations", min_value=10, value=10, step=10)

    # Run single simulation
    dates, portfolio_values, withdrawal_values, start_withdrawal_date, total_withdrawn = simulate_investment(
        initial_deposit,
        monthly_deposit,
        deposit_growth_rate,
        annual_return_rate,
        annual_inflation_rate,
        annual_withdrawal_rate,
        target_annual_living_cost,
        years,
        annual_volatility,
        start_date
    )
    fig = create_plot(dates, portfolio_values, withdrawal_values, start_withdrawal_date)
    st.plotly_chart(fig, use_container_width=True)
    display_summary(start_withdrawal_date, total_withdrawn, portfolio_values, start_date)

    # Monte Carlo simulation
    st.subheader("Monte Carlo Success Probability")
    probability = run_monte_carlo(
        initial_deposit,
        monthly_deposit,
        deposit_growth_rate,
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
        f"and ending with a positive portfolio is **{probability:.2f}%**."
    )

    # Display exactly one meme (centered) based on outcome.
    display_memes(probability)


if __name__ == "__main__":
    main()