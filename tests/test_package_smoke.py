import pandas as pd

from as_tagging import SnapshotProvider, normalize_asn_input, normalize_asn_list


class InMemoryProvider(SnapshotProvider):
    def list_snapshots(self):
        return ["2025-01"]

    def get_snapshot(self, date, use_cache=True):
        assert date == "2025-01"
        return pd.DataFrame({"example_feature": [1]}, index=pd.Index(["13335"], name="asn"))


def test_public_package_imports_and_normalization():
    assert normalize_asn_input("AS13335") == "13335"
    assert normalize_asn_list(["AS13335", 15169]) == ["13335", "15169"]
    assert InMemoryProvider().get_snapshot("2025-01").loc["13335", "example_feature"] == 1
