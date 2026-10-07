"""
Manually verified mobile and non-mobile ASes extracted from new_ml_tagging_final_mobile.ipynb.

Sources in notebook:
- correct: explicitly mobile (manually verified)
- partial_correct: mobile (edge cases; comment: "Claro, Digicel, DauphinTelecom, Flow, Apua,
  HuronTel, Focus Broadband, Quadro, SPM Telecom, United Telephone Association, iTel, CIKTel,
  Viaero, XTel (not like retail, but 5G Cellular), PineBelt")
- small_labeled_mobile: mobile (subset of correct)
- incorrect: explicitly non-mobile (manually verified)
- small_neg_list: non-mobile (comment: "Tempest hosting, ...")
- arin_non_mobile (inline, when arin_non_mobile.json not used): ["40627"] - non-mobile

Note: arin_mobile.json and arin_non_mobile.json contain additional labels (34 mobile, 725 non-mobile
in the full notebook run) but are external files not in this repo.
"""

# Mobile (correct) - manually verified
# From: correct + partial_correct, deduplicated
MOBILE_CORRECT = sorted({
    10396, 13771, 33392, 15344, 36511, 35900, 6639, 30689, 396357, 11594,
    40945, 32020, 11139, 11084, 17356, 33749, 25914, 394311, 3695, 30174,
    16696, 26288, 54614, 22324, 32307, 2740, 36827, 14813, 14593, 15146,
    396304, 46408, 14434, 3855, 46650, 40786, 22933, 21928, 8014, 14638,
    33576, 22581, 7922, 16705, 33582, 395561, 852, 21996, 36549, 22069,
    399724, 577, 11426, 11351, 33363, 46198, 10292, 7018, 701, 812, 7992,
    6327, 6167, 11290, 11427, 22773, 20001, 10796, 20115, 5769, 21744, 855,
    27653, 14754, 27775, 52253, 52233, 27745, 27725, 11816, 27651, 27781,
    8151, 27800, 27895, 8048, 52260, 27882, 6400, 11081, 27734, 27831,
    10620, 6147, 22047, 12252, 23201, 10269, 7418, 19863, 6057, 11556,
    7303, 27665, 27660, 28118, 52262, 18809, 27773, 6568, 27759, 28104,
    22085, 52228, 3816, 11830, 28036, 7122, 23243, 52362, 26611, 14709,
    52242, 262197, 27699, 13999, 11888, 28006, 28573, 25607, 26599, 4230,
    18881, 22927,
    # partial_correct: mobile (edge cases per notebook comment)
    8057, 22351,
})

# Non-mobile (incorrect) - manually verified
# From: incorrect + small_neg_list + arin_non_mobile inline ["40627"], deduplicated
NON_MOBILE_INCORRECT = sorted({
    13335, 36290, 16413, 22995, 5650, 19323, 30165, 54665, 15305, 263763,
    27694, 27947, 52468, 27924, 52263, 21826, 17072, 272809, 27923, 265691,
    270963, 262146, 27729,
    # small_neg_list (non-mobile; comment: "Tempest hosting, ...")
    209, 16437, 14061, 393275, 36231, 21859, 394684, 22363, 16509, 3549,
    19551, 8070, 19237, 268581,
    # arin_non_mobile inline (when JSON not used) - explicitly non-mobile
    40627,
})

# Small labeled subset (10 mobile) used as minimal seed in notebook
SMALL_LABELED_MOBILE = [10396, 13771, 33392, 15344, 36511, 35900, 6639, 30689, 396357, 11594]

# Convenience: lists for semi-supervised tagging
positive_asns = [str(a) for a in MOBILE_CORRECT]
negative_asns = [str(a) for a in NON_MOBILE_INCORRECT]

if __name__ == "__main__":
    print("Mobile (correct):", len(MOBILE_CORRECT))
    print("Non-mobile (incorrect):", len(NON_MOBILE_INCORRECT))
