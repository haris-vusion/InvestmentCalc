import streamlit as st
import plotly.graph_objects as go
import random
import math
import os
from datetime import datetime
from dateutil.relativedelta import relativedelta

# 1) Tax & Utility Functions
BASE_PERSONAL_ALLOWANCE = 12570
BASE_BASIC_RATE_LIMIT   = 50270
BASE_HIGHER_RATE_LIMIT  = 125140

def calc_tax_annual(gross, pa, brt, hrt):
    if gross <= 0:
        return 0.0
    tax = 0.0
    if gross <= pa:
        return 0.0
    basic_portion = max(0, min(gross, brt) - pa)
    higher_portion = max(0, min(gross, hrt) - brt) if gross > brt else 0
    additional_portion = max(0, gross - hrt) if gross > hrt else 0
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
    pa  = BASE_PERSONAL_ALLOWANCE * factor
    brt = BASE_BASIC_RATE_LIMIT  * factor
    hrt = BASE_HIGHER_RATE_LIMIT * factor
    return pa, brt, hrt

# 2) Simulation
def simulate_investment(
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
):
    total_months = years * 12
    monthly_mean_return = (1 + annual_return_rate) ** (1/12) - 1
    monthly_std = annual_volatility / (12 ** 0.5)
    monthly_inflation_rate = (1 + annual_inflation_rate) ** (1/12) - 1
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

        # Check if we can start withdrawing
        required_portfolio = (this_month_net_cost * 12) / annual_withdrawal_rate
        if not withdrawing and portfolio_value >= required_portfolio:
            withdrawing = True
            start_withdrawal_date = current_date

        # Grow monthly deposit
        if month > 0:
            current_monthly_deposit *= (1 + deposit_growth_rate)
        portfolio_value += current_monthly_deposit

        # Market returns
        current_month_return = random.gauss(monthly_mean_return, monthly_std)
        portfolio_value *= (1 + current_month_return)

        # Withdraw if in withdrawal mode
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
    dates = None

    for _ in range(num_simulations):
        d, pv, wv, _, _ = simulate_investment(
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
        if dates is None:
            dates = d
        for i in range(total_months):
            aggregated_portfolio[i] += pv[i]
            aggregated_withdrawal[i] += wv[i]

    avg_portfolio = [p / num_simulations for p in aggregated_portfolio]
    avg_withdrawal = [w / num_simulations for w in aggregated_withdrawal]
    return dates, avg_portfolio, avg_withdrawal

# 3) Plot & Summaries
def create_plot(dates, portfolio_values, withdrawal_values):
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=portfolio_values,
            mode='lines',
            line=dict(color='blue', width=3),
            name='Avg. Portfolio Value (£)'
        )
    )
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=withdrawal_values,
            mode='lines',
            line=dict(color='red', width=2, dash='dot'),
            name='Avg. Monthly Withdrawal (£)'
        )
    )
    fig.update_layout(
        title="Average Portfolio Growth & Withdrawals Over Time",
        xaxis_title="Date",
        yaxis_title="£",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=60, b=40)
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
            f"(~**{years_to_withdraw:.2f} years** into the simulation)."
        )
        st.write(f"• Final average portfolio value: £{portfolio_values[-1]:,.2f}")
        st.write(f"• Total average withdrawn: £{total_withdrawn:,.2f}")

# 4) Monte Carlo & Memes
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
        _, portfolio_vals, _, start_withdrawal_date, _ = simulate_investment(
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
        if start_withdrawal_date is not None and portfolio_vals[-1] > 0:
            success_count += 1
    return (success_count / num_simulations) * 100

def display_memes(probability):
    """Show exactly one meme, centered, based on outcome."""
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

# 5) Main App
def main():
    # Minimal custom CSS to style the success probability
    st.markdown("""
        <style>
        .big-metric {
            text-align: center;
            font-size: 48px;
            font-weight: 600;
            color: #2ecc71;
            margin-top: 10px;
            margin-bottom: 10px;
        }
        .subtle-box {
            background-color: #1c1c1c;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 20px;
        }
        </style>
    """, unsafe_allow_html=True)

    st.title("Haris' Lods of Emone Simulator")
    st.write(
        "A sleek, user-focused simulator that factors in a simplified UK tax system, "
        "inflation-adjusted brackets, and monthly deposit growth. Your living cost is treated **post-tax**."
    )

    # Sidebar
    st.sidebar.header("Simulation Parameters")
    start_date = st.sidebar.date_input(
        "Starting Date",
        value=datetime.today(),
        help="When does your simulation begin?"
    )
    initial_deposit = st.sidebar.number_input(
        "Initial Deposit (£)",
        min_value=0,
        value=1000,
        step=500,
        help="How much money do you start with?"
    )
    monthly_deposit = st.sidebar.number_input(
        "Monthly Deposit (£)",
        min_value=0,
        value=100,
        step=50,
        help="How much you contribute each month initially."
    )
    annual_inflation_rate = st.sidebar.slider(
        "Annual Inflation Rate (%)",
        0.0, 7.0, 4.8, 0.2,
        help="Expected annual inflation, also used to adjust tax brackets every 5 years."
    ) / 100.0
    deposit_growth_rate = st.sidebar.slider(
        "Monthly Deposit Growth Rate (%)",
        0.0, annual_inflation_rate * 100, annual_inflation_rate * 30, 0.1,
        help="Rate at which your monthly deposit grows over time."
    ) / 100.0
    annual_return_rate = st.sidebar.slider(
        "Annual Return Rate (%)",
        0.0, 20.0, 14.8, 0.2,
        help="Projected average annual return on your portfolio."
    ) / 100.0
    annual_withdrawal_rate = st.sidebar.slider(
        "Annual Withdrawal Rate (%)",
        0.0, 20.0, 4.0, 0.5,
        help="Percentage of the portfolio you withdraw annually once you start living off it."
    ) / 100.0
    target_annual_living_cost = st.sidebar.number_input(
        "Target Net Annual Living Cost (£)",
        min_value=0,
        value=30000,
        step=1000,
        help="How much you want to spend (post-tax) each year."
    )
    years = st.sidebar.slider(
        "Number of Years to Simulate",
        1, 100, 20, 1,
        help="How many years does this simulation run?"
    )
    annual_volatility = st.sidebar.slider(
        "Annual Volatility (%)",
        0.0, 30.0, 15.0, 0.2,
        help="Market volatility (standard deviation). Higher means bigger swings."
    ) / 100.0
    num_simulations = st.sidebar.number_input(
        "Monte Carlo Simulations",
        min_value=10,
        value=50,
        step=10,
        help="Number of runs for both the average curve and success probability."
    )

    # 1) Compute success probability up front and display as big metric
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
    st.markdown(f"<div class='subtle-box'><div class='big-metric'>Monte Carlo Success Probability: {probability:.2f}%</div></div>", unsafe_allow_html=True)

    # 2) Plot average results
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
    fig = create_plot(dates, avg_portfolio, avg_withdrawal)
    st.plotly_chart(fig, use_container_width=True)

    # 3) Run one simulation for the summary
    sim_dates, portfolio_vals, withdraw_vals, start_wd_date, total_wd = simulate_investment(
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
    display_summary(start_wd_date, total_wd, portfolio_vals, start_date)

    # 4) Meme time
    display_memes(probability)


if __name__ == "__main__":
    main()

