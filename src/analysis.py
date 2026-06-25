from __future__ import annotations

from collections import Counter, defaultdict

from rdkit import Chem, DataStructs
from rdkit.Chem import rdFingerprintGenerator
from rdkit.ML.Cluster import Butina


MORGAN_GENERATOR = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)


def _fingerprints(rows: list[dict]):
    fps = []
    valid_indices = []
    for idx, row in enumerate(rows):
        mol = Chem.MolFromSmiles(row.get("smiles", ""))
        if mol is None:
            continue
        fps.append(MORGAN_GENERATOR.GetFingerprint(mol))
        valid_indices.append(idx)
    return valid_indices, fps


def cluster_candidates(rows: list[dict], distance_threshold: float = 0.55) -> list[dict]:
    if not rows:
        return []
    enriched = [dict(row) for row in rows]
    valid_indices, fps = _fingerprints(enriched)
    if len(fps) < 2:
        for idx in valid_indices:
            enriched[idx]["cluster_id"] = 1
            enriched[idx]["cluster_size"] = 1
            enriched[idx]["cluster_representative"] = True
        return enriched

    distances = []
    for i in range(1, len(fps)):
        similarities = DataStructs.BulkTanimotoSimilarity(fps[i], fps[:i])
        distances.extend(1.0 - similarity for similarity in similarities)
    clusters = Butina.ClusterData(distances, len(fps), distance_threshold, isDistData=True)

    for cluster_id, cluster in enumerate(clusters, start=1):
        cluster_size = len(cluster)
        representative_local_idx = cluster[0]
        for local_idx in cluster:
            row_idx = valid_indices[local_idx]
            enriched[row_idx]["cluster_id"] = cluster_id
            enriched[row_idx]["cluster_size"] = cluster_size
            enriched[row_idx]["cluster_representative"] = local_idx == representative_local_idx

    for row in enriched:
        row.setdefault("cluster_id", None)
        row.setdefault("cluster_size", 0)
        row.setdefault("cluster_representative", False)
    return enriched


def property_summary(rows: list[dict]) -> dict:
    if not rows:
        return {}
    summary = {
        "candidate_count": len(rows),
        "cluster_count": len({row.get("cluster_id") for row in rows if row.get("cluster_id") is not None}),
    }
    for key in ["mw", "clogp", "tpsa", "score", "similarity"]:
        values = [float(row[key]) for row in rows if row.get(key) is not None]
        if not values:
            continue
        summary[f"{key}_min"] = round(min(values), 4)
        summary[f"{key}_median"] = round(sorted(values)[len(values) // 2], 4)
        summary[f"{key}_max"] = round(max(values), 4)
    return summary


def group_summary(rows: list[dict], key: str) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[str(row.get(key) or "unknown")].append(row)

    summary = []
    for group, items in groups.items():
        scores = [float(item.get("score") or 0.0) for item in items]
        summary.append(
            {
                key: group,
                "count": len(items),
                "top_score": round(max(scores), 2) if scores else None,
                "top_candidate": max(items, key=lambda item: float(item.get("score") or 0.0)).get("candidate_id"),
            }
        )
    return sorted(summary, key=lambda item: (-item["count"], str(item[key])))


def candidate_class_counts(rows: list[dict]) -> list[dict]:
    counts = Counter(row.get("enumeration_type") or "unknown" for row in rows)
    return [{"enumeration_type": key, "count": value} for key, value in counts.most_common()]


def candidate_diversity_bucket(row: dict) -> str:
    enumeration = str(row.get("enumeration_type") or "unknown")
    replacement_class = str(row.get("replacement_class") or "")
    if enumeration == "scaffold_replacement":
        if replacement_class in {"ring_expansion", "ring_contraction"}:
            return "ring_size_operator"
        if "saturated" in replacement_class or "bioisostere" in replacement_class:
            return f"scaffold:{replacement_class or 'bioisostere'}"
        return f"scaffold:{replacement_class or 'other'}"
    if enumeration in {"rgroup_network_replacement", "ring_network_replacement"}:
        return f"network:{row.get('site_type') or 'site'}"
    if enumeration == "functional_group_replacement":
        return f"functional:{row.get('functional_rule_id') or row.get('site_type') or 'rule'}"
    return f"substituent:{row.get('site_type') or 'site'}"


def select_diverse_top_n(rows: list[dict], top_n: int = 20, per_cluster_limit: int = 1) -> list[dict]:
    if top_n <= 0:
        return []
    sorted_rows = sorted(rows, key=lambda item: float(item.get("score") or 0.0), reverse=True)
    selected: list[dict] = []
    cluster_counts: Counter = Counter()

    for row in sorted_rows:
        bucket = row.get("diversity_bucket") or candidate_diversity_bucket(row)
        cluster_id = f"{bucket}:{row.get('cluster_id') or row.get('candidate_id')}"
        if cluster_counts[cluster_id] >= per_cluster_limit:
            continue
        selected.append(row)
        cluster_counts[cluster_id] += 1
        if len(selected) >= top_n:
            break

    if len(selected) < top_n:
        selected_ids = {row.get("candidate_id") for row in selected}
        for row in sorted_rows:
            if row.get("candidate_id") in selected_ids:
                continue
            selected.append(row)
            if len(selected) >= top_n:
                break

    return selected


def annotate_diverse_top_n(rows: list[dict], top_n: int = 20, per_cluster_limit: int = 1) -> list[dict]:
    enriched = []
    for row in rows:
        item = dict(row)
        item["diversity_bucket"] = item.get("diversity_bucket") or candidate_diversity_bucket(item)
        enriched.append(item)
    selected = select_diverse_top_n(enriched, top_n=top_n, per_cluster_limit=per_cluster_limit)
    selected_ids = {row.get("candidate_id"): idx for idx, row in enumerate(selected, start=1)}
    for row in enriched:
        diverse_rank = selected_ids.get(row.get("candidate_id"))
        row["diverse_pick"] = diverse_rank is not None
        row["diverse_rank"] = diverse_rank
    return enriched
