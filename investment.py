import streamlit as st
import plotly.graph_objects as go
import random
import math
import os
from datetime import datetime
from dateutil.relativedelta import relativedelta

########################
# 1) TAX & UTILITY FUNCS
########################
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
    """Binary search to find how much gross is needed to net a certain amount."""
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
    Every 5 years, tax brackets get inflated by (1 + annual_inflation_rate)^5.
    year // 5 => how many 5-year chunks have passed.
    """
    inflation_periods = year // 5
    factor = (1 + annual_inflation_rate) ** (5 * inflation_periods)
    pa  = BASE_PERSONAL_ALLOWANCE * factor
    brt = BASE_BASIC_RATE_LIMIT  * factor
    hrt = BASE_HIGHER_RATE_LIMIT * factor
    return pa, brt, hrt

############################
# 2) SIMULATION LOGIC
############################
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
    """
    Runs a single simulation path with monthly compounding, monthly deposit growth,
    and an automatic 'switch to withdrawals' once the portfolio can sustain the net annual cost.
    """
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

        # Adjust net monthly cost by inflation
        if month == 0:
            this_month_net_cost = initial_monthly_net_cost
        else:
            this_month_net_cost = monthly_net_costs[-1] * (1 + monthly_inflation_rate)

        # Check if we should start withdrawing
        required_portfolio = (this_month_net_cost * 12) / annual_withdrawal_rate
        if not withdrawing and portfolio_value >= required_portfolio:
            withdrawing = True
            start_withdrawal_date = current_date

        # Grow the monthly deposit
        if month > 0:
            current_monthly_deposit *= (1 + deposit_growth_rate)
        portfolio_value += current_monthly_deposit

        # Random monthly return
        current_month_return = random.gauss(monthly_mean_return, monthly_std)
        portfolio_value *= (1 + current_month_return)

        # If withdrawing, figure out the gross needed to net this_month_net_cost
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

        # Record the data
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
    """
    Runs multiple simulations and returns the average portfolio & withdrawals over time.
    """
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

############################
# 3) PLOTTING & SUMMARIES
############################
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

##############################
# 4) MONTE CARLO & MEMES
##############################
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
    """
    Counts how many simulations both start withdrawals AND end with a positive portfolio balance.
    """
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
        # "Success" if it eventually started withdrawing AND had > 0 left at the end
        if start_withdrawal_date is not None and portfolio_vals[-1] > 0:
            success_count += 1
    return (success_count / num_simulations) * 100

def display_memes(probability):
    """Show exactly one meme, centered, based on outcome."""
    good_memes_folder = "goodMemes"
    bad_memes_folder = "badMemes"

    if probability >= 50:
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

##############################
# 5) MAIN APP
##############################
def main():
    st.set_page_config(page_title="Haris' Lods of Emone", layout="wide")

    # Minimal custom CSS
    st.markdown("""
        <style>
        .small-metric {
            text-align: center;
            font-size: 32px;
            font-weight: 600;
            margin-top: 10px;
            margin-bottom: 10px;
        }
        .subtle-box {
            background-color: #1c1c1c;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 20px;
        }
        .center-text {
            text-align: center;
        }
        </style>
    """, unsafe_allow_html=True)

    st.title("Haris' Lods of Emone Simulator")
    st.write(
        "A sleek, user-focused simulator that factors in a simplified UK tax system, "
        "inflation-adjusted brackets, and monthly deposit growth. Your living cost is treated **post-tax**."
    )

    # Default param dictionary (in PERCENT for rates)
    default_params = {
        "start_date": datetime.today().date(),
        "initial_deposit": 1000,
        "monthly_deposit": 100,
        "annual_inflation_rate": 4.8,   # means 4.8% annual
        "deposit_growth_rate": 0.1,     # means 0.1% monthly in the slider
        "annual_return_rate": 14.8,     # means 14.8% annual
        "annual_withdrawal_rate": 4.0,  # means 4.0% annual
        "target_annual_living_cost": 30000,
        "years": 20,
        "annual_volatility": 15.0,      # means 15% standard deviation
        "num_simulations": 50
    }

    # === SIDEBAR ===
    st.sidebar.header("Simulation Parameters")
    user_start_date = st.sidebar.date_input(
        "Starting Date",
        value=default_params["start_date"],
        help="When does your simulation begin?"
    )
    user_initial_deposit = st.sidebar.number_input(
        "Initial Deposit (£)",
        min_value=0,
        value=default_params["initial_deposit"],
        step=500,
        help="How much money do you start with?"
    )
    user_monthly_deposit = st.sidebar.number_input(
        "Monthly Deposit (£)",
        min_value=0,
        value=default_params["monthly_deposit"],
        step=50,
        help="How much you contribute each month initially."
    )
    user_annual_inflation_rate = st.sidebar.slider(
        "Annual Inflation Rate (%)",
        0.0, 7.0,
        default_params["annual_inflation_rate"],
        0.2,
        help="Expected annual inflation, also used to adjust tax brackets every 5 years."
    )
    # This slider is for monthly deposit growth, 0.0% to 2.0% monthly, default 0.1% monthly
    user_deposit_growth_rate = st.sidebar.slider(
        "Monthly Deposit Growth Rate (%)",
        0.0, 2.0,
        default_params["deposit_growth_rate"],
        0.1,
        help="Rate at which your monthly deposit grows each month."
    )
    user_annual_return_rate = st.sidebar.slider(
        "Annual Return Rate (%)",
        0.0, 20.0,
        default_params["annual_return_rate"],
        0.2,
        help="Projected average annual return on your portfolio."
    )
    user_annual_withdrawal_rate = st.sidebar.slider(
        "Annual Withdrawal Rate (%)",
        0.0, 20.0,
        default_params["annual_withdrawal_rate"],
        0.5,
        help="Percentage of the portfolio you withdraw annually once you start living off it."
    )
    user_target_annual_living_cost = st.sidebar.number_input(
        "Target Net Annual Living Cost (£)",
        min_value=0,
        value=default_params["target_annual_living_cost"],
        step=1000,
        help="How much you want to spend (post-tax) each year."
    )
    user_years = st.sidebar.slider(
        "Number of Years to Simulate",
        1, 100,
        default_params["years"],
        1,
        help="How many years does this simulation run?"
    )
    user_annual_volatility = st.sidebar.slider(
        "Annual Volatility (%)",
        0.0, 30.0,
        default_params["annual_volatility"],
        0.2,
        help="Market volatility (standard deviation). Higher means bigger swings."
    )
    user_num_simulations = st.sidebar.number_input(
        "Monte Carlo Simulations",
        min_value=10,
        value=default_params["num_simulations"],
        step=10,
        help="Number of runs for both the average curve and success probability."
    )

    # === Convert user params from % => decimal where needed ===
    user_annual_inflation_rate   /= 100.0  # e.g., 4.8 => 0.048
    user_deposit_growth_rate     /= 100.0  # e.g., 0.1 => 0.001
    user_annual_return_rate      /= 100.0  # e.g., 14.8 => 0.148
    user_annual_withdrawal_rate  /= 100.0  # e.g., 4.0 => 0.04
    user_annual_volatility       /= 100.0  # e.g., 15.0 => 0.15

    # Function to check float equality
    def floats_match(a, b):
        return abs(a - b) < 1e-9

    # We'll consider them "unchanged" if all match exactly (within float tolerance).
    unchanged = (
        (user_start_date == default_params["start_date"]) and
        (user_initial_deposit == default_params["initial_deposit"]) and
        (user_monthly_deposit == default_params["monthly_deposit"]) and
        floats_match(user_annual_inflation_rate * 100.0, default_params["annual_inflation_rate"]) and
        floats_match(user_deposit_growth_rate * 100.0, default_params["deposit_growth_rate"]) and
        floats_match(user_annual_return_rate * 100.0, default_params["annual_return_rate"]) and
        floats_match(user_annual_withdrawal_rate * 100.0, default_params["annual_withdrawal_rate"]) and
        (user_target_annual_living_cost == default_params["target_annual_living_cost"]) and
        (user_years == default_params["years"]) and
        floats_match(user_annual_volatility * 100.0, default_params["annual_volatility"]) and
        (user_num_simulations == default_params["num_simulations"])
    )

    # If unchanged, prompt user to tweak something
    if unchanged:
        st.markdown("## Welcome!")
        st.write("Adjust the parameters in the sidebar to begin the auto-run simulation.\n\n"
                 "You'll see the results here as soon as you change something!")
        return  # End the main() here, no simulation is shown

    # === Monte Carlo success probability ===
    probability = run_monte_carlo(
        user_initial_deposit,
        user_monthly_deposit,
        user_deposit_growth_rate,
        user_annual_return_rate,
        user_annual_inflation_rate,
        user_annual_withdrawal_rate,
        user_target_annual_living_cost,
        user_years,
        user_annual_volatility,
        user_start_date,
        int(user_num_simulations)
    )

    # Color the success probability metric
    if probability >= 50:
        color = "#2ecc71"  # green
    else:
        color = "#e74c3c"  # red

    st.markdown(
        f"<div class='subtle-box'><div class='small-metric' style='color:{color}'>"
        f"Monte Carlo Success Probability: {probability:.2f}%"
        f"</div></div>",
        unsafe_allow_html=True
    )

    # === SINGLE RUN (for chart + summary) ===
    single_dates, single_portfolio, single_withdrawals, single_start_wd, single_total_wd = simulate_investment(
        user_initial_deposit,
        user_monthly_deposit,
        user_deposit_growth_rate,
        user_annual_return_rate,
        user_annual_inflation_rate,
        user_annual_withdrawal_rate,
        user_target_annual_living_cost,
        user_years,
        user_annual_volatility,
        user_start_date
    )

    # === AVERAGE RUN (for chart) ===
    avg_dates, avg_portfolio, avg_withdrawals = simulate_average_simulation(
        user_initial_deposit,
        user_monthly_deposit,
        user_deposit_growth_rate,
        user_annual_return_rate,
        user_annual_inflation_rate,
        user_annual_withdrawal_rate,
        user_target_annual_living_cost,
        user_years,
        user_annual_volatility,
        user_start_date,
        int(user_num_simulations)
    )

    # === CREATE COMBINED FIGURE ===
    fig = go.Figure()

    # Single-run portfolio
    fig.add_trace(
        go.Scatter(
            x=single_dates,
            y=single_portfolio,
            mode='lines',
            line=dict(color='blue', width=2),
            name='Single-Run Portfolio (£)'
        )
    )
    # Single-run withdrawals
    fig.add_trace(
        go.Scatter(
            x=single_dates,
            y=single_withdrawals,
            mode='lines',
            line=dict(color='red', width=2, dash='dot'),
            name='Single-Run Monthly Withdrawal (£)'
        )
    )

    # Average portfolio
    fig.add_trace(
        go.Scatter(
            x=avg_dates,
            y=avg_portfolio,
            mode='lines',
            line=dict(color='green', width=2),
            name='Average Portfolio (£)'
        )
    )
    # Average withdrawals
    fig.add_trace(
        go.Scatter(
            x=avg_dates,
            y=avg_withdrawals,
            mode='lines',
            line=dict(color='orange', width=2, dash='dot'),
            name='Average Monthly Withdrawal (£)'
        )
    )

    # Add a vertical line if single-run withdrawals started, and annotate it
    if single_start_wd is not None:
        # Convert datetime to ISO format for the x-axis if needed
        x_value = single_start_wd.isoformat() if isinstance(single_start_wd, datetime) else single_start_wd
        fig.add_vline(x=x_value, line_width=2, line_dash="dash", line_color="black")
        fig.add_annotation(
            x=x_value,
            y=max(single_portfolio),
            text="Withdrawal Start",
            showarrow=True,
            arrowhead=2,
            ax=0,
            ay=-40,
            font=dict(color="green"),
            arrowcolor="green"
        )
    # Format the y-axis to 1 decimal place
    fig.update_yaxes(tickformat=".1f")

    fig.update_layout(
        title="Portfolio Growth & Withdrawals Over Time",
        xaxis_title="Date",
        yaxis_title="£",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=60, b=40)
    )
    st.plotly_chart(fig, use_container_width=True)

    # === SINGLE RUN SUMMARY ===
    display_summary(single_start_wd, single_total_wd, single_portfolio, user_start_date)

    # === INFLATION EQUIVALENCE NOTE ===
    # e.g., after 'user_years' years, how much is £100 today in future terms?
    inflation_factor = (1 + user_annual_inflation_rate) ** user_years
    st.write(
        f"**Inflation Check:** With {user_annual_inflation_rate*100:.2f}% annual inflation over {user_years} years, "
        f"£100 **today** will be roughly £{100 * inflation_factor:.2f} in year {user_years}."
    )

    # === Meme time ===
    display_memes(probability)

if __name__ == "__main__":
    main()
