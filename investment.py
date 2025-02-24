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
BASE_BASIC_RATE_LIMIT = 50270
BASE_HIGHER_RATE_LIMIT = 125140


def calc_tax_annual(gross, pa, brt, hrt):
    """Simple tiered UK tax calculation given inflated personal allowances and thresholds."""
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
    return gross - calc_tax_annual(gross, pa, brt, hrt)


def required_gross_annual_for_net_annual(net_annual, pa, brt, hrt):
    """Binary search to find how much gross is needed to net a certain amount."""
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
    """Inflate all bracket cutoffs by some factor."""
    pa = BASE_PERSONAL_ALLOWANCE * factor
    brt = BASE_BASIC_RATE_LIMIT * factor
    hrt = BASE_HIGHER_RATE_LIMIT * factor
    return pa, brt, hrt


################################
# 1A) HELPER TO CHECK RETIREMENT
################################
def can_retire_now(portfolio_value, annual_withdrawal_rate, current_annual_cost, pa, brt, hrt):
    """
    Return True if the net withdrawal (after tax) from portfolio_value * annual_withdrawal_rate
    is enough to cover current_annual_cost.
    """
    gross_withdrawal = annual_withdrawal_rate * portfolio_value
    tax_on_withdrawal = calc_tax_annual(gross_withdrawal, pa, brt, hrt)
    net_withdrawal = gross_withdrawal - tax_on_withdrawal
    return net_withdrawal >= current_annual_cost


############################
# 2) SIMULATION LOGIC
############################
def simulate_investment(
        initial_deposit,
        monthly_deposit,
        deposit_growth_rate,  # e.g. 0.005 => 0.5% growth each month
        annual_return_rate,   # e.g. 0.07 => 7% annual
        annual_inflation_rate,  # e.g. 0.02 => 2% annual
        annual_withdrawal_rate, # e.g. 0.04 => 4% annual
        target_annual_living_cost,  # e.g. 30000
        years,
        annual_volatility,    # e.g. 0.15 => 15% stdev
        start_date,
):
    """
    Monthly simulation:
      • We deposit every month until we retire.
      • 'Retire' (flip to withdraw mode) as soon as net withdrawal at the chosen withdrawal rate
        can cover your desired annual net cost (including inflation).
      • Once withdrawing, no more deposits, but we withdraw monthly = (annual withdrawal) / 12,
        inflated each month, subject to partial if portfolio is too small.
      • Returns are random draws from a normal distribution with mean = monthly_mean_return, std = monthly_std.
      • Inflation is applied monthly to your target living cost (and to the tax bracket cutoffs).
    """
    total_months = years * 12

    # Convert to monthly
    monthly_return_mean = (1 + annual_return_rate) ** (1 / 12) - 1
    monthly_std = annual_volatility / (12 ** 0.5)
    monthly_inflation = (1 + annual_inflation_rate) ** (1 / 12) - 1

    # Current scenario
    portfolio_value = float(initial_deposit)
    withdrawing = False
    start_withdrawal_date = None
    total_withdrawn = 0.0

    # time-series tracking
    dates_list = []
    portfolio_values = []
    withdrawal_values = []

    # NEW: Track potential monthly net withdrawal if we retired *this* month
    potential_monthly_net_withdrawals = []

    current_monthly_deposit = float(monthly_deposit)
    current_annual_cost = float(target_annual_living_cost)

    # Because we do monthly inflation, keep track of a "tax bracket inflation factor" each month
    tax_factor = 1.0

    for m in range(total_months):
        current_date = start_date + relativedelta(months=m)

        # 1) deposit (if not retired)
        if not withdrawing:
            portfolio_value += current_monthly_deposit
            # deposit grows for next month
            current_monthly_deposit *= (1 + deposit_growth_rate)

        # 2) apply monthly random return
        monthly_return = random.gauss(monthly_return_mean, monthly_std)
        portfolio_value *= (1 + monthly_return)

        # 3) check if we have 'enough' to retire, using net withdrawal logic
        pa, brt, hrt = get_tax_brackets_for_factor(tax_factor)
        if (not withdrawing) and can_retire_now(portfolio_value, annual_withdrawal_rate, current_annual_cost, pa, brt, hrt):
            withdrawing = True
            start_withdrawal_date = current_date

        # 4) if withdrawing, withdraw monthly from the portfolio.
        #    The "annual withdrawal" is the needed gross for your annual cost, i.e. enough to net current_annual_cost.
        #    We'll compute that by reversing the tax function each month.
        #    Alternatively, you can keep the existing approach to ensure you always withdraw exactly what's needed.
        if withdrawing:
            needed_gross_annual = required_gross_annual_for_net_annual(current_annual_cost, pa, brt, hrt)
            monthly_gross_needed = needed_gross_annual / 12.0
            if portfolio_value >= monthly_gross_needed:
                withdrawal_amt = monthly_gross_needed
            else:
                # partial withdrawal if not enough
                withdrawal_amt = max(0, portfolio_value)
            portfolio_value -= withdrawal_amt
        else:
            withdrawal_amt = 0.0

        total_withdrawn += withdrawal_amt

        # track for plotting
        dates_list.append(current_date)
        portfolio_values.append(portfolio_value)
        withdrawal_values.append(withdrawal_amt)

        # 5) calculate potential net withdrawal *if* you retired now
        #    (this is purely for visualization, doesn't affect actual logic)
        gross_withdrawal_now = annual_withdrawal_rate * portfolio_value
        tax_on_withdrawal_now = calc_tax_annual(gross_withdrawal_now, pa, brt, hrt)
        net_annual_withdrawal_now = gross_withdrawal_now - tax_on_withdrawal_now
        potential_monthly_net_withdrawal = net_annual_withdrawal_now / 12.0
        potential_monthly_net_withdrawals.append(potential_monthly_net_withdrawal)

        # 6) inflation increments for next month
        current_annual_cost *= (1 + monthly_inflation)
        tax_factor *= (1 + monthly_inflation)

    return dates_list, portfolio_values, withdrawal_values, start_withdrawal_date, total_withdrawn, potential_monthly_net_withdrawals


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
    """Average out multiple runs of the above simulation."""
    total_months = years * 12
    aggregated_portfolio = [0.0] * total_months
    aggregated_withdrawal = [0.0] * total_months
    aggregated_potential_net_wd = [0.0] * total_months
    dates = None

    for _ in range(num_simulations):
        d, pv, wv, _, _, pmwd = simulate_investment(
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
            aggregated_potential_net_wd[i] += pmwd[i]

    avg_portfolio = [p / num_simulations for p in aggregated_portfolio]
    avg_withdrawal = [w / num_simulations for w in aggregated_withdrawal]
    avg_potential_wd = [x / num_simulations for x in aggregated_potential_net_wd]
    return dates, avg_portfolio, avg_withdrawal, avg_potential_wd


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
    We'll say a run is 'successful' if:
      (a) We eventually start withdrawing (i.e. can retire), AND
      (b) The portfolio is above zero at the end of the simulation.
    """
    successes = 0
    for _ in range(num_simulations):
        _, pv, _, wd_date, _, _ = simulate_investment(
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
        if wd_date is not None and pv[-1] > 0:
            successes += 1
    return (successes / num_simulations) * 100


def display_summary_for_average(dates, portfolio, withdrawals, start_date):
    import streamlit as st
    first_withdraw_idx = None
    for i, w in enumerate(withdrawals):
        if w > 1e-9:
            first_withdraw_idx = i
            break

    total_withdrawn = sum(withdrawals)
    final_portfolio = portfolio[-1]

    st.subheader("Summary (Average Simulation)")

    if first_withdraw_idx is None:
        st.write("• The average simulation never reached the threshold to retire.")
        st.write(f"• Final average portfolio value: £{final_portfolio:,.2f}")
        st.write("• Total average withdrawn: £0.00")
    else:
        start_wd_date = dates[first_withdraw_idx]
        yrs_into_sim = (start_wd_date - start_date).days / 365.25
        st.write(f"• Retire withdrawals began on {start_wd_date.strftime('%Y-%m-%d')} (~{yrs_into_sim:.2f} years in).")
        st.write(f"• Final average portfolio value: £{final_portfolio:,.2f}")
        st.write(f"• Total average withdrawn: £{total_withdrawn:,.2f}")


def display_memes(probability):
    """
    Example usage showing a random 'good meme' vs 'bad meme'.
    Adjust folder paths or remove entirely if you just want a silly placeholder.
    """
    good_memes_folder = "goodMemes"
    bad_memes_folder = "badMemes"

    if probability >= 50:
        st.markdown("### Congratulations! It's a Good Outcome Meme Break")
        meme_folder = good_memes_folder
    else:
        st.markdown("### Ouch... It's a Bad Outcome Meme Break")
        meme_folder = bad_memes_folder

    try:
        all_files = os.listdir(meme_folder)
        image_files = [f for f in all_files if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))]
        if not image_files:
            st.write(f"No meme images found in '{meme_folder}'.")
            return
        chosen_meme = random.choice(image_files)
        meme_path = os.path.join(meme_folder, chosen_meme)
        col1, col2, col3 = st.columns([1, 2, 1])
        col2.image(meme_path, caption=chosen_meme, width=300)
    except Exception as e:
        st.write(f"Could not load memes from folder '{meme_folder}'")
        st.write(e)


##############################
# 5) MAIN APP
##############################
def main():
    st.set_page_config(page_title="Haris' Lods of Emone", layout="wide")

    st.title("Haris' Lods of Emone Simulator")
    st.write(
        "A quick simulation that invests monthly and flips to withdrawals "
        "as soon as the portfolio can sustain your target annual net cost "
        "at your chosen withdrawal rate."
    )

    # Default parameter dictionary (in PERCENT for rates)
    default_params = {
        "start_date": datetime.today().date(),
        "initial_deposit": 5000,
        "monthly_deposit": 100,
        "annual_inflation_rate": 4.8,  # 4.8% annual
        "deposit_growth_rate": 0.5,  # 0.5% monthly deposit growth
        "annual_return_rate": 14.8,  # 14.8% annual
        "annual_withdrawal_rate": 4.0,  # 4% annual
        "target_annual_living_cost": 30000,
        "years": 100,
        "annual_volatility": 15.0,  # 15% stdev
        "num_simulations": 50
    }

    # === SIDEBAR ===
    st.sidebar.header("Simulation Parameters")
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
    user_monthly_deposit = st.sidebar.number_input(
        "Monthly Deposit (£)",
        min_value=0,
        value=default_params["monthly_deposit"],
        step=50
    )
    user_annual_inflation_rate = st.sidebar.slider(
        "Annual Inflation Rate (%)",
        0.0, 7.0,
        default_params["annual_inflation_rate"], 0.1
    )
    user_deposit_growth_rate = st.sidebar.slider(
        "Monthly Deposit Growth Rate (%)",
        0.0, 2.0,
        default_params["deposit_growth_rate"], 0.1
    )
    user_annual_return_rate = st.sidebar.slider(
        "Annual Return Rate (%)",
        0.0, 20.0,
        default_params["annual_return_rate"], 0.1
    )
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
    user_years = st.sidebar.slider(
        "Number of Years to Simulate",
        1, 100,
        default_params["years"]
    )
    user_annual_volatility = st.sidebar.slider(
        "Annual Volatility (%)",
        0.0, 30.0,
        default_params["annual_volatility"], 0.1
    )
    user_num_sims = st.sidebar.number_input(
        "Monte Carlo Simulations",
        min_value=10,
        value=default_params["num_simulations"],
        step=10
    )

    # Convert percentages => decimals
    user_annual_inflation_rate /= 100.0
    user_deposit_growth_rate /= 100.0
    user_annual_return_rate /= 100.0
    user_annual_withdrawal_rate /= 100.0
    user_annual_volatility /= 100.0

    # === RUN MONTE CARLO
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
        user_num_sims
    )

    color = "#2ecc71" if probability >= 50 else "#e74c3c"
    st.markdown(
        f"""
        <div style="background-color: #1c1c1c; border-radius: 8px; padding: 15px; margin-bottom: 20px;">
            <div style="text-align:center; font-size:32px; font-weight:600; color:{color}">
                Monte Carlo Success Probability: {probability:.2f}%
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # === AVERAGE SIM
    avg_dates, avg_portfolio, avg_withdrawals, avg_potential_wds = simulate_average_simulation(
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
        user_num_sims
    )

    # Build a yearly plot
    fig = go.Figure()
    total_months = len(avg_dates)
    # Group by year-ends
    year_end_indices = range(11, total_months, 12)
    year_end_x = []
    year_end_port = []
    year_end_wd = []
    year_end_potential = []

    for idx in year_end_indices:
        if idx >= total_months:
            break
        year_end_x.append(avg_dates[idx])
        year_end_port.append(avg_portfolio[idx])
        # sum monthly withdrawals for that year block
        year_start = idx - 11
        sum_wd = sum(avg_withdrawals[year_start:idx + 1])
        year_end_wd.append(sum_wd)
        year_end_potential.append(avg_potential_wds[idx])  # just pick the last monthly potential in that year

    fig.add_trace(
        go.Scatter(
            x=year_end_x,
            y=year_end_port,
            name="Year-End Portfolio (Avg)",
            mode='lines+markers',
            line=dict(color='cyan', width=3)
        )
    )
    fig.add_trace(
        go.Scatter(
            x=year_end_x,
            y=year_end_wd,
            name="Yearly Withdrawal (Avg)",
            mode='lines+markers',
            line=dict(color='yellow', width=2, dash='dot')
        )
    )
    fig.add_trace(
        go.Scatter(
            x=year_end_x,
            y=year_end_potential,
            name="Potential Net WD (Year-End)",
            mode='lines+markers',
            line=dict(color='magenta', width=2)
        )
    )

    # Mark the first year we see withdrawals
    first_wd_idx = next((i for i, w in enumerate(year_end_wd) if w > 0), None)
    if first_wd_idx is not None:
        x_val = year_end_x[first_wd_idx]
        y_val = year_end_port[first_wd_idx]
        fig.add_vline(x=x_val, line_width=2, line_dash="dash", line_color="green")
        fig.add_annotation(
            x=x_val,
            y=y_val,
            text="Withdrawal Start (Avg)",
            showarrow=True,
            arrowhead=2,
            ax=0,
            ay=-40,
            font=dict(color="green"),
            arrowcolor="green"
        )

    fig.update_layout(
        title="Portfolio Growth & Withdrawals (Yearly, Average of Simulations)",
        xaxis_title="Date",
        yaxis_title="£",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=60, b=40)
    )

    st.plotly_chart(fig, use_container_width=True)

    # Show textual summary
    display_summary_for_average(avg_dates, avg_portfolio, avg_withdrawals, user_start_date)

    # Simple inflation check
    infl_factor = (1 + user_annual_inflation_rate) ** user_years
    st.write(
        f"**Inflation Check:** With {user_annual_inflation_rate * 100:.2f}% annual inflation over {user_years} years, "
        f"£100 today is about £{100 * infl_factor:,.2f} in year {user_years}."
    )

    # Meme break
    display_memes(probability)


if __name__ == "__main__":
    main()