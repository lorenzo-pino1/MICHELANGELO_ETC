import os
import json
import matplotlib.pyplot as plt
import re

# File paths to compare
file1_path = "output_CRIRES_ETC_command_line/nominal_dit150_3244.json"
file2_path = "BACKUP_old_templates_and_outputs/output_CRIRES_ETC_command_line/nominal_dit150_L3244.json"

def load_json(filepath):
    """Loads JSON file safely."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")
    with open(filepath, 'r') as f:
        return json.load(f)

def flatten_dict(d, parent_key='', sep='.'):
    """Recursively flattens nested dictionaries/lists into dot-notation paths."""
    items = []
    if isinstance(d, dict):
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, (dict, list)) and not is_numerical_array(v):
                items.extend(flatten_dict(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
    elif isinstance(d, list):
        for idx, item in enumerate(d):
            new_key = f"{parent_key}[{idx}]"
            if isinstance(item, (dict, list)) and not is_numerical_array(item):
                items.extend(flatten_dict(item, new_key, sep=sep).items())
            else:
                items.append((new_key, item))
    return dict(items)

def normalize_detector_name(det_str):
    """
    Normalizes '1', 'det1', 'detector1', 'DETECTOR 1' all to 'detector1'.
    """
    det_str = str(det_str).strip().lower()
    # Extract digits from string
    digits = re.findall(r'\d+', det_str)
    if digits:
        return f"detector{digits[0]}"
    return det_str  # fallback for non-numeric detector labels like 'global_psf'

def is_numerical_array(val):
    """Checks if a value is a non-empty list containing only numbers."""
    if isinstance(val, list) and len(val) > 0:
        return all(isinstance(x, (int, float)) for x in val)
    return False

def build_order_map(data):
    """
    Parses both Old Format (data.orders) and New Format (data.plots.spectra / psfs)
    into a unified structure: order_map[order_id][detector_name] = flattened_dict
    """
    order_map = {}
    data_section = data.get("data", {})
    
    # -------------------------------------------------------------
    # 1. Check for OLD FORMAT: data -> orders -> detectors
    # -------------------------------------------------------------
    if "orders" in data_section and isinstance(data_section["orders"], list):
        for o in data_section["orders"]:
            order_id = str(o.get("order", "unknown"))
            if order_id not in order_map:
                order_map[order_id] = {}
            for det in o.get("detectors", []):
                raw_name = str(det.get("name", det.get("detector_name", "det1")))
                det_name = normalize_detector_name(raw_name)
                order_map[order_id][det_name] = flatten_dict(det)

    # -------------------------------------------------------------
    # 2. Check for NEW FORMAT: data -> plots -> spectra / psfs
    # -------------------------------------------------------------
    elif "plots" in data_section and isinstance(data_section["plots"], dict):
        plots = data_section["plots"]
        
        # Parse 'spectra' array
        spectra = plots.get("spectra", [])
        for item in spectra:
            order_id = str(item.get("order", "1"))
            # det_name = str(item.get("detector_name", "det1"))
            
            # # Standardize detector string ("detector1" -> "detector1")
            raw_name = item.get("detector_name", item.get("name", "1"))
            det_name = normalize_detector_name(raw_name)

            if order_id not in order_map:
                order_map[order_id] = {}
            if det_name not in order_map[order_id]:
                order_map[order_id][det_name] = {}
                
            flat_item = flatten_dict(item)
            order_map[order_id][det_name].update(flat_item)

        # Parse standalone 'psfs' array (assigned under order "1", det "global_psf" if omitted)
        psfs = plots.get("psfs", [])
        if psfs:
            if "1" not in order_map:
                order_map["1"] = {}
            flat_psfs = flatten_dict({"psfs": psfs})
            order_map["1"]["global_psf"] = flat_psfs

    return order_map

def main():
    print("Loading datasets...")
    data1 = load_json(file1_path)
    data2 = load_json(file2_path)
    
    label1 = data1.get("application", {}).get("executiondate", file1_path)
    label2 = data2.get("application", {}).get("executiondate", file2_path)
    
    map1 = build_order_map(data1)
    map2 = build_order_map(data2)
    
    output_dir = "comparison_plots"
    os.makedirs(output_dir, exist_ok=True)
    
    # Optional sorting helper
    try:
        from natsort import natsorted
        sort_fn = natsorted
    except ImportError:
        sort_fn = sorted

    all_orders = sort_fn(list(set(map1.keys()) & set(map2.keys())))
    print(f"Found {len(all_orders)} matching order key(s) between the two files.")
    
    plot_count = 0
    for order in all_orders:
        det_map1 = map1[order]
        det_map2 = map2[order]
        common_dets = sort_fn(list(set(det_map1.keys()) & set(det_map2.keys())))

        for det in common_dets:
            flat1 = det_map1[det]
            flat2 = det_map2[det]
            
            # Match quantity paths
            common_quantities = sort_fn(list(set(flat1.keys()) & set(flat2.keys())))
            
            for qty in common_quantities:
                val1 = flat1[qty]
                val2 = flat2[qty]

                # Verify that both are 1D plottable numerical arrays
                if is_numerical_array(val1) and is_numerical_array(val2):
                    plt.figure(figsize=(10, 5))
                    
                    plt.plot(val1, label=f"File 1 ({label1})", alpha=0.8, lw=1.5)
                    plt.plot(val2, label=f"File 2 ({label2})", alpha=0.8, lw=1.5, linestyle="--")

                    clean_title = qty.replace("plots.", "").replace("noise_components.", "").upper()
                    plt.title(f"Order {order} | {det} : {clean_title}", fontsize=12, fontweight='bold')
                    plt.xlabel("Index")
                    plt.ylabel("Value")
                    plt.grid(True, linestyle=":", alpha=0.6)
                    plt.legend(loc="best", fontsize=9)
                    
                    # Sanitize key string for safe filename save
                    safe_qty = qty.replace("[", "_").replace("]", "").replace(".", "_")
                    filename = f"order_{order}_{det}_{safe_qty}.png"
                    
                    plt.savefig(os.path.join(output_dir, filename), dpi=150, bbox_inches='tight')
                    plt.close()
                    plot_count += 1

    print(f"Done! Successfully saved {plot_count} comparison plot(s) inside '{output_dir}/'.")

if __name__ == "__main__":
    main()