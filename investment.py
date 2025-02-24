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

BASE_PERSONAL_ALLOWANCE = 12570
BASE_BASIC_RATE_LIMIT = 50270  # up to this (minus PA) taxed at 20%
BASE_HIGHER_RATE_LIMIT = 125140  # up to this taxed at 40%, above taxed at 45%


def calc_tax_annual(gross, pa, brt, hrt):
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
    return gross - calc_tax_annual(gross, pa, brt, hrt)


def required_gross_annual_for_net_annual(net_annual, pa, brt, hrt):
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
        deposit_growth_rate,  # monthly deposit increases by this rate each month
        annual_return_rate,
        annual_inflation_rate,
        annual_withdrawal_rate,
        target_annual_living_cost,  # desired net (post-tax) annual cost
        years,
        annual_volatility,
        start_date
):
    total_months = years * 12
    monthly_mean_return = (1 + annual_return_rate) ** (1 / 12) - 1
    monthly_std = annual_volatility / (12 ** 0.5)
    monthly_inflation_rate = (1 + annual_inflation_rate) ** (1 / 12) - 1

    initial_monthly_net_cost = target_annual_living_cost / 12.0

    portfolio_value = initial_deposit
    start_withdrawal_date = None
    withdrawing = False
    total_withdrawn = 0.0

    dates_list = []
    portfolio_values = []
    withdrawal_values = []
    monthly_net_costs = []

    current_monthly_deposit = monthly_deposit

    for month in range(total_months):
        current_date = start_date + relativedelta(months=+month)

        if month == 0:
            this_month_net_cost = initial_monthly_net_cost
        else:
            this_month_net_cost = monthly_net_costs[-1] * (1 + monthly_inflation_rate)

        # Determine when to start withdrawing:
        required_portfolio = (this_month_net_cost * 12) / annual_withdrawal_rate
        if not withdrawing and portfolio_value >= required_portfolio:
            withdrawing = True
            start_withdrawal_date = current_date

        if month > 0:
            current_monthly_deposit *= (1 + deposit_growth_rate)
        portfolio_value += current_monthly_deposit

        current_month_return = random.gauss(monthly_mean_return, monthly_std)
        portfolio_value *= (1 + current_month_return)

        if withdrawing:
            current_year = month // 12
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


def simulate_average_simulation(
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
    total_months = years * 12
    aggregated_portfolio = [0.0] * total_months
    aggregated_withdrawal = [0.0] * total_months

    for _ in range(num_simulations):
        dates, pv, wv, _, _ = simulate_investment(
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
        for i in range(total_months):
            aggregated_portfolio[i] += pv[i]
            aggregated_withdrawal[i] += wv[i]

    avg_portfolio = [x / num_simulations for x in aggregated_portfolio]
    avg_withdrawal = [x / num_simulations for x in aggregated_withdrawal]
    return dates, avg_portfolio, avg_withdrawal


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
            name='Average Portfolio Value (£)'
        )
    )
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=withdrawal_values,
            mode='lines',
            line=dict(color='red', width=2, dash='dot'),
            name='Average Monthly Withdrawal (£)'
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
        title="Average Portfolio Growth & Withdrawals Over Time",
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
        st.write(f"• Final average portfolio value: £{portfolio_values[-1]:,.2f}")
        st.write("• Total average withdrawn: £0.00 (No withdrawals were made.)")
    else:
        years_to_withdraw = (start_withdrawal_date - start_date).days / 365.25
        st.write(
            f"• Withdrawals began on **{start_withdrawal_date.strftime('%Y-%m-%d')}** "
            f"(after about **{years_to_withdraw:.2f} years**)."
        )
        st.write(f"• Final average portfolio value: £{portfolio_values[-1]:,.2f}")
        st.write(f"• Total average withdrawn: £{total_withdrawn:,.2f}")


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
        _, pv, _, start_withdrawal_date, _ = simulate_investment(
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
        if start_withdrawal_date is not None and pv[-1] > 0:
            success_count += 1
    return (success_count / num_simulations) * 100


def display_memes(probability):
    """
    Display exactly ONE meme, centered, based on outcome.
    We'll say 'good' if probability >= 80, else 'bad'.
    """
    good_memes_folder = "goodMemes"
    bad_memes_folder = "badMemes"

    if probability >= 80:
        meme_folder = good_memes_folder
        st.markdown("### Congratulations! It's a Good Outcome Meme Break")
    else:
        meme_folder = badMemes_folder
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
# 5) Main App with Enhanced UI
# -------------------------------

def main():
    # Inject some custom CSS to style the Monte Carlo metric prominently.
    st.markdown("""
        <style>
        .success-metric {
            text-align: center;
            font-size: 48px;
            font-weight: bold;
            color: #2ecc71;
            background-color: #ecf0f1;
            padding: 20px;
            border-radius: 10px;
            margin: 20px 0;
        }
        </style>
        """, unsafe_allow_html=True)

    st.title("Haris' Lods of Emone Simulator")
    st.write(
        "This simulator uses a simplified UK tax model—with brackets adjusted for inflation every 5 years—"
        "and growing monthly deposits to compute your investment outcomes. Your target living cost is considered **post-tax**."
    )

    # Sidebar with parameters and inline help text
    st.sidebar.header("Simulation Parameters")
    start_date = st.sidebar.date_input("Starting Date", value=datetime.today(),
                                       help="Select the simulation start date.")
    initial_deposit = st.sidebar.number_input("Initial Deposit (£)", min_value=0, value=1000, step=500,
                                              help="Your starting lump sum investment.")
    monthly_deposit = st.sidebar.number_input("Monthly Deposit (£)", min_value=0, value=100, step=50,
                                              help="The amount you contribute monthly initially.")
    annual_inflation_rate = st.sidebar.slider("Annual Inflation Rate (%)", 0.0, 7.0, 4.8, 0.2,
                                              help="The expected annual inflation rate (affects living cost and tax brackets).") / 100.0
    deposit_growth_rate = st.sidebar.slider(
        "Monthly Deposit Growth Rate (%)",
        0.0, annual_inflation_rate * 100, annual_inflation_rate * 30, 0.1,
        help="The rate at which your monthly deposit increases over time (capped by inflation)."
    ) / 100.0
    annual_return_rate = st.sidebar.slider("Annual Return Rate (%)", 0.0, 20.0, 14.8, 0.2,
                                           help="The expected annual return rate of your investments.") / 100.0
    annual_withdrawal_rate = st.sidebar.slider("Annual Withdrawal Rate (%)", 0.0, 20.0, 4.0, 0.5,
                                               help="The rate at which you plan to withdraw from your portfolio annually.") / 100.0
    st.sidebar.markdown("**Target Net Annual Living Cost**")
    target_annual_living_cost = st.sidebar.number_input(
        "Post-tax Annual Living Cost (£)",
        min_value=0,
        value=30000,
        step=1000,
        help="The net amount you want to spend per year (after taxes)."
    )
    years = st.sidebar.slider("Number of Years to Simulate", 1, 100, 20, 1,
                              help="The total simulation duration in years.")
    annual_volatility = st.sidebar.slider("Annual Volatility (%)", 0.0, 30.0, 15.0, 0.2,
                                          help="The expected volatility of the market (higher values mean more risk).") / 100.0
    num_simulations = st.sidebar.number_input("Monte Carlo Simulations", min_value=10, value=50, step=10,
                                              help="The number of simulation runs to compute average outcomes and success probability.")

    # Run average simulation over many runs for the graph.
    dates, avg_portfolio, avg_withdrawal = simulate_average_simulation(
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
    fig = create_plot(dates, avg_portfolio, avg_withdrawal, None)
    st.plotly_chart(fig, use_container_width=True)

    # Run one simulation for summary display (to get a representative withdrawal start date, etc.)
    sim_dates, portfolio_values, withdrawal_values, start_withdrawal_date, total_withdrawn = simulate_investment(
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
    display_summary(start_withdrawal_date, total_withdrawn, portfolio_values, start_date)

    # Run Monte Carlo simulation for success probability
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

    # Prominently display the Monte Carlo Success Probability
    st.markdown(f"<div class='success-metric'>Monte Carlo Success Probability: {probability:.2f}%</div>",
                unsafe_allow_html=True)

    # Display one centered meme based on the outcome.
    display_memes(probability)


if __name__ == "__main__":
    main()
