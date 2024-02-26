import numpy as np

from message_ix import Scenario, make_df
from message_ix.testing import make_dantzig

# First model year of the Dantzig scenario
_year = 1963


def calculate_activity(scen, tec="transport_from_seattle"):
    return scen.var("ACT").groupby(["technology", "mode"])["lvl"].sum().loc[tec]


def test_add_bound_activity_up(request, test_mp):
    scen = make_dantzig(test_mp, request=request, solve=True, quiet=True)

    # data for act bound
    exp = 0.5 * calculate_activity(scen).sum()
    name = "bound_activity_up"
    data = make_df(
        name,
        node_loc="seattle",
        technology="transport_from_seattle",
        year_act=_year,
        time="year",
        unit="cases",
        mode="to_chicago",
        value=exp,
    )

    # test limiting one mode
    clone = scen.clone(scenario=f"{scen.scenario} cloned", keep_solution=False)

    with clone.transact():
        clone.add_par("bound_activity_up", data)

    clone.solve(quiet=True)
    obs = calculate_activity(clone).loc["to_chicago"]
    assert np.isclose(obs, exp)

    orig_obj = scen.var("OBJ")["lvl"]
    new_obj = clone.var("OBJ")["lvl"]
    assert new_obj >= orig_obj


def test_add_bound_activity_up_all_modes(request, test_mp):
    """

    This test specifically has two solutions for which the `OBJ` function is the same
    therefore the lpmethod must be set to "2".

    With lpmethod=2:

    - "transport_from_seattle" needs to provide "to_chicago" with 300.
    - in the unconstrained example seattle delivers 50 to "to_new_york" and 300
      "to_chicago".
    - additional 275 to "to_new_york" comes from san-diego.
    - the activity bound for "transport_from_seattle" (see below) below is therefore
      set to 325.

    With  lpmethod=4:

    - the unconstrained example seattle delivers 300 "to_chicago".
    - san-diego delivers 325 to "to_new_york"
    - the resulting bound on activity for seattle, therefore is below what is required
      for "to_chicago".
    """
    scen = make_dantzig(test_mp, request=request, solve=False, quiet=True)
    scen.solve(quiet=True, solve_options=dict(lpmethod=2))

    # data for act bound
    # print(calculate_activity(scen))
    exp = 0.95 * calculate_activity(scen).sum()
    name = "bound_activity_up"
    data = make_df(
        name,
        node_loc="seattle",
        technology="transport_from_seattle",
        year_act=_year,
        time="year",
        unit="cases",
        mode="all",
        value=exp,
    )

    # test limiting all modes
    clone = scen.clone(scenario=f"{scen.scenario} cloned", keep_solution=False)

    with clone.transact():
        clone.add_par(name, data)

    clone.solve(quiet=True, solve_options=dict(lpmethod=2))
    obs = calculate_activity(clone).sum()
    assert np.isclose(obs, exp)

    orig_obj = scen.var("OBJ")["lvl"]
    new_obj = clone.var("OBJ")["lvl"]
    assert new_obj >= orig_obj


def test_commodity_share_up(request, test_mp):
    """Original Solution
    ----------------

         lvl         mode    mrg   node_loc                technology
    0  350.0   production  0.000    seattle             canning_plant
    1   50.0  to_new-york  0.000    seattle    transport_from_seattle
    2  300.0   to_chicago  0.000    seattle    transport_from_seattle
    3    0.0    to_topeka  0.036    seattle    transport_from_seattle
    4  600.0   production  0.000  san-diego             canning_plant
    5  275.0  to_new-york  0.000  san-diego  transport_from_san-diego
    6    0.0   to_chicago  0.009  san-diego  transport_from_san-diego
    7  275.0    to_topeka  0.000  san-diego  transport_from_san-diego

    Constraint Test
    ---------------

    Seattle canning_plant production (original: 350) is limited to 50% of all
    transport_from_san-diego (original: 550). Expected outcome: some increase
    of transport_from_san-diego with some decrease of production in seattle.
    """

    # data for share bound
    def calc_share(s):
        a = s.var(
            "ACT", filters={"technology": ["canning_plant"], "node_loc": ["seattle"]}
        )["lvl"][0]
        b = calculate_activity(s, tec="transport_from_san-diego").sum()
        return a / b

    common = dict(shares="test-share", node_share="seattle")

    # common operations for both subtests
    def add_data(s, map_df):
        with s.transact("Add share_commodity_up"):
            s.add_cat("technology", "share", "canning_plant")
            s.add_cat("technology", "total", "transport_from_san-diego")

            s.add_set("shares", "test-share")

            s.add_set(
                "map_shares_commodity_share",
                make_df(
                    "map_shares_commodity_share",
                    **common,
                    node="seattle",
                    type_tec="share",
                    mode="production",
                    commodity="cases",
                    level="supply",
                ),
            )
            s.add_set("map_shares_commodity_total", map_df)
            s.add_par(
                "share_commodity_up",
                make_df(
                    "share_commodity_up",
                    **common,
                    year_act=_year,
                    time="year",
                    unit="%",
                    value=0.5,
                ),
            )

    # initial data
    scen = make_dantzig(test_mp, solve=True, request=request)

    exp = 0.5

    # check shares orig, should be bigger than expected bound
    orig = calc_share(scen)
    assert orig > exp

    # add share constraints for modes explicitly
    map_df = make_df(
        "map_shares_commodity_total",
        **common,
        node="san-diego",
        type_tec="total",
        mode=["to_new-york", "to_chicago", "to_topeka"],
        commodity="cases",
        level="supply",
    )
    clone = scen.clone(scenario=f"{scen.scenario} share_mode_list", keep_solution=False)
    add_data(clone, map_df)
    clone.solve(quiet=True)

    # check shares new, should be lower than expected bound
    obs = calc_share(clone)
    assert obs <= exp

    # check obj
    orig_obj = scen.var("OBJ")["lvl"]
    new_obj = clone.var("OBJ")["lvl"]
    assert new_obj >= orig_obj

    # add share constraints with mode == 'all'
    map_df2 = map_df.assign(mode="all")
    clone2 = scen.clone(
        scenario=f"{scen.scenario} share_all_modes", keep_solution=False
    )
    add_data(clone2, map_df2)
    clone2.solve(quiet=True)

    # check shares new, should be lower than expected bound
    obs2 = calc_share(clone2)
    assert obs2 <= exp

    # it should also be the same as the share with explicit modes
    assert obs == obs2

    # check obj
    orig_obj = scen.var("OBJ")["lvl"]
    new_obj = clone2.var("OBJ")["lvl"]
    assert new_obj >= orig_obj


def test_commodity_share_lo(request, test_mp):
    scen = make_dantzig(test_mp, request=request, solve=True, quiet=True)

    # data for share bound
    def calc_share(s: Scenario) -> float:
        """Compute the share achieved on scenario `s`."""
        a = calculate_activity(s, tec="transport_from_seattle").loc["to_new-york"]
        b = calculate_activity(s, tec="transport_from_san-diego").loc["to_new-york"]
        return a / (a + b)

    exp = 1.0 * calc_share(scen)

    # add share constraints
    clone = scen.clone(keep_solution=False)

    with clone.transact("Add share constraints"):
        clone.add_set("shares", "test-share")

        common = dict(
            mode="all", node="new-york", node_share="new-york", shares="test-share"
        )

        # Add category and mapping set elements
        for tt, members in (
            ("share", ["transport_from_seattle"]),
            ("total", ["transport_from_seattle", "transport_from_san-diego"]),
        ):
            clone.add_cat("technology", tt, members)
            name = f"map_shares_commodity_{tt}"
            clone.add_set(
                name,
                make_df(
                    name, **common, type_tec=tt, commodity="cases", level="consumption"
                ),
            )

        # Add the value of the constraint
        name = "share_commodity_lo"
        clone.add_par(
            name,
            make_df(
                name, time="year", unit="cases", value=exp, year_act=_year, **common
            ),
        )

    clone.solve(quiet=True)

    # The solution has the expected share
    assert np.isclose(exp, calc_share(clone))

    # Objective function value is larger in the clone (with constraints) than the
    # original scenario (unconstrained)
    assert clone.var("OBJ")["lvl"] >= scen.var("OBJ")["lvl"]


def test_add_share_mode_up(request, test_mp):
    scen = make_dantzig(test_mp, request=request, solve=True, quiet=True)

    # data for share bound
    def calc_share(s):
        a = calculate_activity(s, tec="transport_from_seattle").loc["to_chicago"]
        b = calculate_activity(s, tec="transport_from_seattle").sum()
        return a / b

    exp = 0.95 * calc_share(scen)

    # add share constraints
    clone = scen.clone(scenario=f"{scen.scenario} share_mode_up", keep_solution=False)

    with clone.transact("Add share_mode_up"):
        clone.add_set("shares", "test-share")
        clone.add_par(
            "share_mode_up",
            make_df(
                "share_mode_up",
                shares="test-share",
                node_share="seattle",
                technology="transport_from_seattle",
                mode="to_chicago",
                year_act=_year,
                time="year",
                unit="cases",
                value=exp,
            ),
        )

    clone.solve(quiet=True)
    obs = calc_share(clone)
    assert np.isclose(obs, exp)

    orig_obj = scen.var("OBJ")["lvl"]
    new_obj = clone.var("OBJ")["lvl"]
    assert new_obj >= orig_obj


def test_add_share_mode_lo(request, test_mp):
    scen = make_dantzig(test_mp, solve=True, request=request, quiet=True)

    # data for share bound
    def calc_share(s):
        a = calculate_activity(s, tec="transport_from_san-diego").loc["to_new-york"]
        b = calculate_activity(s, tec="transport_from_san-diego").sum()
        return a / b

    exp = 1.05 * calc_share(scen)

    # add share constraints
    clone = scen.clone(scenario=f"{scen.scenario} cloned", keep_solution=False)
    with clone.transact():
        clone.add_set("shares", "test-share")
        clone.add_par(
            "share_mode_lo",
            make_df(
                "share_mode_lo",
                shares="test-share",
                node_share="san-diego",
                technology="transport_from_san-diego",
                mode="to_new-york",
                year_act=_year,
                time="year",
                unit="cases",
                value=exp,
            ),
        )

    clone.solve(quiet=True)

    obs = calc_share(clone)
    assert np.isclose(obs, exp)

    orig_obj = scen.var("OBJ")["lvl"]
    new_obj = clone.var("OBJ")["lvl"]
    assert new_obj >= orig_obj
