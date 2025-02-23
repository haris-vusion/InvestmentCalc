import streamlit as st
import plotly.graph_objects as go
import random
import math
from datetime import datetime
from dateutil.relativedelta import relativedelta


def simulate_investment(
        initial_deposit,
        monthly_deposit,
        annual_return_rate,
        annual_inflation_rate,
        annual_withdrawal_rate,
        target_annual_living_cost,
        years,
        annual_volatility,
        start_date
):
    """
    Simulate an investment strategy with random market returns based on historical volatility,
    using dates on the x-axis. Enjoy watching your money age gracefully (or not).
    """
    total_months = years * 12
    monthly_mean_return = (1 + annual_return_rate) ** (1 / 12) - 1
    monthly_std = annual_volatility / (12 ** 0.5)
    monthly_inflation_rate = (1 + annual_inflation_rate) ** (1 / 12) - 1
    initial_monthly_cost = target_annual_living_cost / 12.0

    portfolio_value = initial_deposit
    start_withdrawal_date = None
    withdrawing = False
    total_withdrawn = 0.0

    dates_list = []
    portfolio_values = []
    withdrawal_values = []
    monthly_costs = []

    for month in range(total_months):
        current_date = start_date + relativedelta(months=+month)

        # Adjust monthly cost for inflation
        if month == 0:
            this_month_cost = initial_monthly_cost
        else:
            this_month_cost = monthly_costs[-1] * (1 + monthly_inflation_rate)

        required_portfolio = (this_month_cost * 12) / annual_withdrawal_rate
        if not withdrawing and portfolio_value >= required_portfolio:
            withdrawing = True
            start_withdrawal_date = current_date

        # Deposit money every month
        portfolio_value += monthly_deposit
        # Grow portfolio using random return
        current_month_return = random.gauss(monthly_mean_return, monthly_std)
        portfolio_value *= (1 + current_month_return)
        # Withdraw monthly cost if applicable
        if withdrawing:
            withdrawal_amt = min(this_month_cost, portfolio_value)
            portfolio_value -= withdrawal_amt
        else:
            withdrawal_amt = 0.0

        total_withdrawn += withdrawal_amt

        dates_list.append(current_date)
        portfolio_values.append(portfolio_value)
        withdrawal_values.append(withdrawal_amt)
        monthly_costs.append(this_month_cost)

    return dates_list, portfolio_values, withdrawal_values, start_withdrawal_date, total_withdrawn


def create_plot(dates, portfolio_values, withdrawal_values, start_withdrawal_date):
    """
    Create an interactive Plotly chart with dates on the x-axis.
    """
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
            line_color="green",
            annotation_text="Withdrawals Begin",
            annotation_position="top right",
            annotation_font_color="green",
            annotation_font_size=12
        )
    fig.update_layout(
        title="Portfolio Growth & Withdrawals Over Time (with Random Volatility)",
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
    """
    Display a summary of your financial journey, complete with actual dates.
    """
    st.subheader("Summary")
    if start_withdrawal_date is None:
        st.write("• The portfolio never reached the threshold to sustain your target living cost. Ouch!")
        st.write(f"• Final portfolio value: £{portfolio_values[-1]:,.2f}")
        st.write("• Total withdrawn: £0.00 (No withdrawals were made.)")
    else:
        years_to_withdraw = (start_withdrawal_date - start_date).days / 365.25
        st.write(
            f"• Started withdrawing on **{start_withdrawal_date.strftime('%Y-%m-%d')}** (after about **{years_to_withdraw:.2f} years**).")
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
    Run multiple simulations to compute the success probability.
    Success means your portfolio starts withdrawals and ends with a positive balance.
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
    success_probability = (success_count / num_simulations) * 100
    return success_probability


def main():
    st.title("Haris' Lods of Emone Simulator")
    st.write("Simulator to buy more cars and dumb shit")
    st.info("On mobile, tap the menu in the top-left corner to see the Simulation Parameters.")
    st.sidebar.header("Simulation Parameters")
    start_date = st.sidebar.date_input("Starting Date", value=datetime.today())
    initial_deposit = st.sidebar.number_input("Initial Deposit (£)", min_value=0, value=1000, step=500)
    monthly_deposit = st.sidebar.number_input("Monthly Deposit (£) (20% of Income)", min_value=0, value=100, step=50)
    annual_return_rate = st.sidebar.slider("Annual Return Rate (%) (14.8% NASDAQ'S Average)", 0.0, 20.0, 14.8,
                                           0.2) / 100.0
    annual_inflation_rate = st.sidebar.slider("Annual Inflation Rate (%) (4.8% Average)", 0.0, 7.0, 4.8, 0.2) / 100.0
    annual_withdrawal_rate = st.sidebar.slider("Annual Withdrawal Rate (%) (4% Recommended)", 0.0, 20.0, 4.0,
                                               0.5) / 100.0
    target_annual_living_cost = st.sidebar.number_input("Target Annual Living Cost (£)", min_value=0, value=30000,
                                                        step=1000)
    years = st.sidebar.slider("Number of Years to Simulate", 1, 40, 20, 1)
    annual_volatility = st.sidebar.slider("Annual Volatility (%)", 0.0, 50.0, 15.0, 0.5) / 100.0
    num_simulations = st.sidebar.number_input("Monte Carlo Simulations", min_value=100, value=1000, step=100)

    if st.sidebar.button("Run Simulation"):
        dates, portfolio_values, withdrawal_values, start_withdrawal_date, total_withdrawn = simulate_investment(
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
        fig = create_plot(dates, portfolio_values, withdrawal_values, start_withdrawal_date)
        st.plotly_chart(fig, use_container_width=True)
        display_summary(start_withdrawal_date, total_withdrawn, portfolio_values, start_date)

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
            f"Based on {num_simulations} simulations, the probability of this actually working "
            f"(starting withdrawals and ending with a positive balance) is **{probability:.2f}%**."
        )
    else:
        st.info(
            "Tweak the parameters in the sidebar and hit 'Run Simulation' to see how your investing unfolds, for better or worse.")


if __name__ == "__main__":
    main()
