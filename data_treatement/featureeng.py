"""
COMPLETE FIXED Feature Generation Script
All issues resolved:
1. Throughput unit detection (Kbps → Mbps)
2. Realistic latency from SINR (not default 30ms)
3. Realistic BLER calculation
4. Proper MOS scaling with latency penalty
5. PRB utilization with zero-throughput handling
"""

import pandas as pd
import numpy as np

# ----------------------------------------------------------------------------
# THEORETICAL THROUGHPUT (Mbps)
# ----------------------------------------------------------------------------
def calculate_theoretical_max_throughput(sinr_db: float, bandwidth_mhz: float = 20) -> float:
    """Maximum possible throughput at given SINR (Mbps)"""
    
    # SINR to spectral efficiency (bits/Hz)
    if sinr_db >= 25:
        spectral_efficiency = 7.4   # 256QAM
    elif sinr_db >= 20:
        spectral_efficiency = 6.0   # 64QAM high
    elif sinr_db >= 15:
        spectral_efficiency = 4.5   # 64QAM mid
    elif sinr_db >= 10:
        spectral_efficiency = 3.0   # 16QAM high
    elif sinr_db >= 5:
        spectral_efficiency = 1.8   # 16QAM low
    elif sinr_db >= 0:
        spectral_efficiency = 0.8   # QPSK
    else:
        spectral_efficiency = 0.3   # BPSK (very poor)
    
    # PRBs for 20 MHz = 100
    prbs = 100
    
    # MIMO factor (2x2 typical)
    mimo_factor = 2.0
    
    # Throughput = PRBs × spectral_efficiency × MIMO × (1 ms frame factor)
    # Simplified: Mbps = (PRBs × spec_eff × MIMO) / 10
    throughput_mbps = (prbs * spectral_efficiency * mimo_factor) / 10
    
    return min(throughput_mbps, 150)  # Cap at 150 Mbps for LTE


# ----------------------------------------------------------------------------
# FIX 1: Throughput unit detection
# ----------------------------------------------------------------------------
def fix_throughput_units(value, column_name):
    """Detect if value is in Kbps and convert to Mbps"""
    if value > 1000:  # Anything > 1000 is likely Kbps
        return value / 1000
    return value


# ----------------------------------------------------------------------------
# FIX 2: Realistic Latency from SINR (NEW)
# ----------------------------------------------------------------------------
def estimate_latency_from_sinr(sinr_db: float) -> float:
    """
    Generate realistic latency based on SINR.
    Poor SINR = more retransmissions = higher latency
    Reference: 3GPP TR 36.942 - Delay performance vs radio conditions
    """
    if sinr_db >= 15:
        return 25      # Excellent - urban macro cell
    elif sinr_db >= 10:
        return 35      # Good - typical VoLTE
    elif sinr_db >= 5:
        return 60      # Fair - increased retransmissions
    elif sinr_db >= 0:
        return 100     # Poor - noticeable delay
    elif sinr_db >= -5:
        return 200     # Very poor - frequent retransmissions
    else:
        return 350     # Near outage - extreme delay


# ----------------------------------------------------------------------------
# FIX 3: PRB Utilization (with zero-throughput handling)
# ----------------------------------------------------------------------------
def estimate_prb_utilization(throughput_mbps: float, sinr_db: float) -> float:
    """
    PRB utilization = measured throughput / max possible throughput
    If no data transfer, utilization is 0%.
    """
    # If no active data transfer, PRB utilization is 0
    if throughput_mbps <= 0.1:
        return 0.0
    
    max_capacity = calculate_theoretical_max_throughput(sinr_db)
    
    if max_capacity <= 0:
        return 0.0
    
    utilization = (throughput_mbps / max_capacity) * 100
    return min(100, max(0, utilization))


# ----------------------------------------------------------------------------
# FIX 4: BLER (realistic, deterministic)
# ----------------------------------------------------------------------------
def estimate_bler(sinr_db: float, throughput_mbps: float, theoretical_max: float) -> float:
    """
    Realistic BLER estimation based on SINR.
    Reference: 3GPP TS 38.214 link adaptation target 10% BLER
    """
    # Base BLER from SINR (realistic mapping)
    if sinr_db >= 20:
        bler = 1.0       # Excellent
    elif sinr_db >= 15:
        bler = 2.0       # Good
    elif sinr_db >= 10:
        bler = 5.0       # Fair
    elif sinr_db >= 5:
        bler = 10.0      # Target BLER (3GPP standard)
    elif sinr_db >= 0:
        bler = 20.0      # Poor
    elif sinr_db >= -5:
        bler = 35.0      # Very poor
    else:
        bler = 50.0      # Near outage
    
    # Adjust based on throughput ratio (congestion increases effective BLER)
    if theoretical_max > 0 and throughput_mbps > 0:
        throughput_ratio = throughput_mbps / theoretical_max
        if throughput_ratio < 0.3:
            bler = min(60, bler * 1.5)
    
    return min(60, max(0.5, bler))


# ----------------------------------------------------------------------------
# FIX 5: MOS (with realistic latency penalty)
# ----------------------------------------------------------------------------
def estimate_mos(sinr_db: float, latency_ms: float, bler_pct: float) -> float:
    """
    MOS estimation for VoLTE.
    Primary driver is SINR, latency penalty applies above 100ms.
    Reference: ITU-T G.107 E-model
    """
    # Base MOS from SINR (realistic mapping)
    if sinr_db >= 20:
        base_mos = 4.2      # Excellent HD Voice
    elif sinr_db >= 15:
        base_mos = 4.0      # Good
    elif sinr_db >= 10:
        base_mos = 3.5      # Fair
    elif sinr_db >= 5:
        base_mos = 3.0      # Poor
    elif sinr_db >= 0:
        base_mos = 2.5      # Very poor
    elif sinr_db >= -5:
        base_mos = 2.0      # Bad
    else:
        base_mos = 1.5      # Unusable
    
    # Latency penalty (applies above 100ms)
    latency_penalty = 0
    if latency_ms > 300:
        latency_penalty = 0.8
    elif latency_ms > 150:
        latency_penalty = 0.5
    elif latency_ms > 100:
        latency_penalty = 0.2
    
    # BLER penalty (secondary factor)
    bler_penalty = min(0.5, bler_pct / 40)
    
    mos = base_mos - latency_penalty - bler_penalty
    
    return max(1.0, min(4.5, mos))


# ----------------------------------------------------------------------------
# MIMO rank (unchanged - correct)
# ----------------------------------------------------------------------------
def estimate_mimo_rank(sinr_db: float, rsrp_dbm: float = -80) -> int:
    """
    MIMO rank selection based on SINR.
    Reference: 3GPP TR 38.802
    """
    if rsrp_dbm < -120:
        return 1
    if sinr_db < 5:
        return 1
    elif sinr_db < 15:
        return 2
    else:
        return 4


# ----------------------------------------------------------------------------
# MAIN GENERATION FUNCTION
# ----------------------------------------------------------------------------
def generate_operator_features(df: pd.DataFrame, bandwidth_mhz: float = 20) -> pd.DataFrame:
    """Generate operator-side features with all fixes applied"""
    
    df_result = df.copy()
    
    # ========================================================================
    # FIX 1: Throughput unit conversion (Kbps → Mbps if needed)
    # ========================================================================
    if 'throughput_dl' in df_result.columns:
        df_result['throughput_dl_mbps'] = df_result['throughput_dl'].apply(
            lambda x: fix_throughput_units(x, 'throughput_dl')
        )
    else:
        df_result['throughput_dl_mbps'] = 0
    
    if 'throughput_ul' in df_result.columns:
        df_result['throughput_ul_mbps'] = df_result['throughput_ul'].apply(
            lambda x: fix_throughput_units(x, 'throughput_ul')
        )
    else:
        df_result['throughput_ul_mbps'] = 0
    
    # ========================================================================
    # FIX 2: Latency generated from SINR (NOT default 30ms)
    # ========================================================================
    # Generate realistic latency based on SINR
    df_result['latency_ms'] = df_result['sinr'].apply(estimate_latency_from_sinr)
    
    # ========================================================================
    # Calculate theoretical max throughput
    # ========================================================================
    df_result['theoretical_max_mbps'] = df_result['sinr'].apply(
        lambda x: calculate_theoretical_max_throughput(x, bandwidth_mhz)
    )
    
    # ========================================================================
    # PRB Utilization (DL)
    # ========================================================================
    df_result['prb_util_dl_pct'] = df_result.apply(
        lambda row: estimate_prb_utilization(
            row['throughput_dl_mbps'], 
            row['sinr']
        ), axis=1
    )
    
    # ========================================================================
    # PRB Utilization (UL) - similar but UL is weaker
    # ========================================================================
    df_result['prb_util_ul_pct'] = df_result.apply(
        lambda row: estimate_prb_utilization(
            row['throughput_ul_mbps'] * 0.8,  # UL typically less capable
            row['sinr'] - 2                   # UL SINR often lower
        ), axis=1
    )
    
    # ========================================================================
    # MIMO Rank
    # ========================================================================
    df_result['mimo_rank'] = df_result.apply(
        lambda row: estimate_mimo_rank(row['sinr'], row['rsrp'] if 'rsrp' in row else -80),
        axis=1
    )
    
    # ========================================================================
    # BLER (DL)
    # ========================================================================
    df_result['bler_dl_pct'] = df_result.apply(
        lambda row: estimate_bler(
            row['sinr'], 
            row['throughput_dl_mbps'], 
            row['theoretical_max_mbps']
        ), axis=1
    )
    
    # ========================================================================
    # MOS (Voice Quality)
    # ========================================================================
    df_result['mos'] = df_result.apply(
        lambda row: estimate_mos(
            row['sinr'], 
            row['latency_ms'], 
            row['bler_dl_pct']
        ), axis=1
    )
    
    # ========================================================================
    # Clean up temporary columns
    # ========================================================================
    df_result = df_result.drop(columns=['theoretical_max_mbps'])
    
    # Keep original throughput columns? No - replace with Mbps versions
    if 'throughput_dl' in df_result.columns:
        df_result = df_result.drop(columns=['throughput_dl'])
    if 'throughput_ul' in df_result.columns:
        df_result = df_result.drop(columns=['throughput_ul'])
    
    # Rename Mbps columns to original names
    df_result = df_result.rename(columns={
        'throughput_dl_mbps': 'throughput_dl',
        'throughput_ul_mbps': 'throughput_ul'
    })
    
    return df_result


# ----------------------------------------------------------------------------
# EXECUTION
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    
    # Load your data
    df = pd.read_csv("qosbuddy_dataset_final.csv")
    
    # Fill missing values
    df = df.fillna(0)
    
    # Generate features
    df_enhanced = generate_operator_features(df)
    
    # Verify results
    print("\n" + "="*80)
    print("SAMPLE OUTPUT (first 3 rows):")
    print("="*80)
    
    # Show key columns
    key_cols = ['rsrp', 'sinr', 'throughput_dl', 'latency_ms', 
                'prb_util_dl_pct', 'bler_dl_pct', 'mos', 'mimo_rank']
    
    for col in key_cols:
        if col in df_enhanced.columns:
            print(f"{col:20} : {df_enhanced[col].head(3).tolist()}")
    
    # Save
    df_enhanced.to_csv("qosbuddy_dataset_enhanced.csv", index=False)
    print("\n✅ Dataset enhanced successfully!")
    print(f"   Saved to: qosbuddy_dataset_enhanced.csv")
    print(f"   Total rows: {len(df_enhanced)}")