from as_tagging.data.preset_lambda import sibling_transit, public_transit


# Shared regression fixture: a real "Public Transit = True" case.
# customer_set = {100, 200, 300}, sibling_set = {100, 101}
# -> not a subset (200, 300 are non-siblings), so:
#      sibling_transit = False
#      public_transit  = True
CUSTOMER_LIST = ["100", "200", "300"]
SIBLING_LIST = ["100", "101"]


def test_raw_lists_present_computes_directly():
    tags = {
        "caida-asrel_customer_list": CUSTOMER_LIST,
        "inetintel-as2org_sibling_list": SIBLING_LIST,
        # Precomputed columns present too (as on an internal snapshot that also
        # carries them) - raw lists must still take priority and must not be
        # shadowed by these.
        "caida-asrel_customer_all_sibling": True,
        "caida-asrel_customer_has_nonsibling": False,
    }

    assert sibling_transit(tags) is False
    assert public_transit(tags) is True


def test_raw_list_absent_falls_back_to_precomputed_columns():
    tags = {
        "caida-asrel_customer_all_sibling": True,
        "caida-asrel_customer_has_nonsibling": False,
    }

    assert sibling_transit(tags) is True
    assert public_transit(tags) is False


def test_neither_raw_list_nor_precomputed_columns_returns_none():
    tags = {"some_other_feature": 1}

    assert sibling_transit(tags) is None
    assert public_transit(tags) is None


def test_raw_list_present_but_empty_is_not_treated_as_missing():
    # Key present with an empty list is a legitimate "no customers" snapshot
    # row, not a "data unavailable" case - must still compute directly
    # (step 1), not fall through to the precomputed columns/None.
    tags = {
        "caida-asrel_customer_list": [],
        "inetintel-as2org_sibling_list": SIBLING_LIST,
        "caida-asrel_customer_all_sibling": True,
        "caida-asrel_customer_has_nonsibling": True,
    }

    assert sibling_transit(tags) is False
    assert public_transit(tags) is False
