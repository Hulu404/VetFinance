"""Independent computation of expected balances for set01.

Does not import anything from backend/. Pure integer kopecks.
Rule (see set01/README.md): balance(account, as_of) = opening_balance
  + sum(amount) over transactions of that account with opening_date <= date <= as_of
  and status != 'duplicate'. Status 'check' IS included. Transfers are included
  as ordinary signed legs (they cancel out in the clinic total).
"""
import json
import pathlib

BASE = pathlib.Path(__file__).resolve().parent.parent / "set01"


ORDER = ["bank", "vetmanager", "bot", "manual"]


def sources_of(data, acc_ids, as_of):
    """Union of sources of operations included in the sum; fixed order; empty -> ['manual']."""
    used = {t["source"] for t in data["transactions"]
            if t["account_id"] in acc_ids and t["status"] != "duplicate" and t["date"] <= as_of}
    return [x for x in ORDER if x in used] or ["manual"]


def main():
    data = json.loads((BASE / "data.json").read_text(encoding="utf-8"))
    out = {"rule": "opening_balance + sum(amount) for date<=as_of, status!=duplicate", "cases": []}
    for clinic in data["clinics"]:
        cid = clinic["id"]
        accs = [a for a in data["accounts"] if a["clinic_id"] == cid]
        for as_of in data["as_of_cases"]:
            per = {}
            for a in accs:
                s = a["opening_balance"]
                for t in data["transactions"]:
                    if (t["account_id"] == a["id"] and t["status"] != "duplicate"
                            and a["opening_date"] <= t["date"] <= as_of):
                        s += t["amount"]
                per[a["id"]] = s
            by_type = {"bank": 0, "cash": 0}
            for a in accs:
                by_type[a["type"]] += per[a["id"]]
            total = sum(per.values())
            assert total == by_type["bank"] + by_type["cash"]
            # transfers must net to zero within the clinic up to as_of
            trf = sum(t["amount"] for t in data["transactions"]
                      if t["clinic_id"] == cid and t["kind"] == "transfer"
                      and t["status"] != "duplicate" and t["date"] <= as_of)
            assert trf == 0, (cid, as_of, trf)
            out["cases"].append({
                "clinic_id": cid, "as_of": as_of,
                "accounts": per, "total": total, "bank": by_type["bank"], "cash": by_type["cash"],
                "figures": {
                    "balance.total": {
                        "value": total, "unit": "rub",
                        "breakdown": [{"label": a["name"], "value": per[a["id"]], "unit": "rub"} for a in accs],
                        "source": sources_of(data, set(per), as_of)},
                    "balance.bank": {
                        "value": by_type["bank"], "unit": "rub",
                        "breakdown": [{"label": a["name"], "value": per[a["id"]], "unit": "rub"}
                                      for a in accs if a["type"] == "bank"],
                        "source": sources_of(data, {a["id"] for a in accs if a["type"] == "bank"}, as_of)},
                    "balance.cash": {"value": by_type["cash"], "unit": "rub",
                                     "source": sources_of(data, {a["id"] for a in accs if a["type"] == "cash"}, as_of)},
                }})
    (BASE / "expected.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for c in out["cases"]:
        print(c["clinic_id"], c["as_of"], c["total"], c["bank"], c["cash"],
              {k: v["source"] for k, v in c["figures"].items()})


if __name__ == "__main__":
    main()
