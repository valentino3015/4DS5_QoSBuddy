"""
Feature Generation Script for Cellular Network Data
Based on references:
- Salo & Zacarías (2017): PRB utilization from throughput [citation:4][citation:7]
- ITU-T G.107: MOS estimation from latency/packet loss [citation:6][citation:8]
- 3GPP 38.802: MIMO rank from SINR [citation:2]
"""

import pandas as pd
import numpy as np
from typing import Optional

def calculate_theoretical_max_throughput(sinr_db: float, bandwidth_mhz: float = 20) -> float:
    """
    Calculate theoretical max throughput (Mbps) based on SINR.
    
    Reference: Salo & Zacarías (2017) - Cell capacity depends on radio conditions [citation:4]
    Mapping derived from 3GPP CQI-to-MCS-to-throughput tables.
    
    Args:
        sinr_db: Signal-to-Interference+Noise Ratio in dB
        bandwidth_mhz: System bandwidth (default 20 MHz for LTE)
    
    Returns:
        Theoretical maximum throughput in Mbps
    """
    # SINR to MCS mapping (simplified from 3GPP TS 38.214)
    if sinr_db >= 25:
        mcs = 28  # 256QAM
        spectral_efficiency = 7.4
    elif sinr_db >= 20:
        mcs = 24  # 64QAM high
        spectral_efficiency = 6.0
    elif sinr_db >= 15:
        mcs = 20  # 64QAM mid
        spectral_efficiency = 4.5
    elif sinr_db >= 10:
        mcs = 15  # 16QAM high
        spectral_efficiency = 3.0
    elif sinr_db >= 5:
        mcs = 10  # 16QAM low
        spectral_efficiency = 1.8
    elif sinr_db >= 0:
        mcs = 5   # QPSK
        spectral_efficiency = 0.8
    else:
        mcs = 2
        spectral_efficiency = 0.3
    
    # Calculate PRBs based on bandwidth (20 MHz = 100 PRBs)
    prbs = min(100, int(bandwidth_mhz * 5))
    
    # Throughput = PRBs × subframes/sec × bits/PRB × MIMO factor
    # 1000 subframes/sec, each PRB carries spectral_efficiency bits/symbol
    # Simplified: Mbps = PRBs × spectral_efficiency × MIMO_factor
    mimo_factor = 2.0  # Assume 2x2 MIMO for baseline
    
    throughput_mbps = (prbs * spectral_efficiency * mimo_factor) / 10
    
    return min(throughput_mbps, 150)  # Cap at reasonable LTE max


def estimate_prb_utilization(
    throughput_mbps: float, 
    sinr_db: float,
    bandwidth_mhz: float = 20
) -> float:
    """
    Estimate PRB utilization percentage from measured throughput.
    
    Reference: Salo & Zacarías (2017) - "Analysis of LTE Radio Load and User Throughput"
    Model: Throughput = Cell_Capacity / (1 - PRB_utilization)
    Therefore: PRB_utilization = 1 - (Cell_Capacity / Throughput)
    
    Args:
        throughput_mbps: Measured DL throughput
        sinr_db: SINR at measurement point
        bandwidth_mhz: System bandwidth
    
    Returns:
        Estimated PRB utilization percentage (0-100)
    """
    cell_capacity = calculate_theoretical_max_throughput(sinr_db, bandwidth_mhz)
    
    if throughput_mbps <= 0 or cell_capacity <= 0:
        return 0.0
    
    # M/G/1 Processor Sharing model inversion
    # Clamp to prevent extreme values
    utilization = max(0, min(0.95, 1 - (cell_capacity / throughput_mbps)))
    
    # Alternative method: If throughput is near capacity, utilization is high
    if throughput_mbps >= cell_capacity * 0.9:
        utilization = 0.9 + 0.05 * (throughput_mbps / cell_capacity - 0.9) / 0.1
    
    return utilization * 100


def estimate_mimo_rank(sinr_db: float, rsrp_dbm: float = -80) -> int:
    """
    Estimate MIMO rank from SINR.
    
    Reference: 3GPP 38.802 - MIMO layer selection based on SINR [citation:2]
    Additional factor: RSRP below -120 dBm indicates poor coverage forcing rank 1
    
    Args:
        sinr_db: SINR in dB
        rsrp_dbm: RSRP in dBm (optional, for coverage check)
    
    Returns:
        Estimated MIMO rank (1, 2, or 4)
    """
    # Poor coverage forces rank 1
    if rsrp_dbm < -120:
        return 1
    
    # SINR-based rank selection
    if sinr_db < 5:
        return 1  # SISO fallback
    elif sinr_db < 15:
        return 2  # 2x2 MIMO typical
    elif sinr_db < 22:
        return 2  # 2x2 still common
    else:
        return 4  # 4x4 MIMO possible with good SINR


def estimate_bler(
    sinr_db: float, 
    throughput_mbps: float, 
    theoretical_max: Optional[float] = None
) -> float:
    """
    Estimate Block Error Rate percentage.
    
    Reference: Link adaptation targets 10% BLER [citation:2]
    BLER increases when SINR cannot support the MCS required for observed throughput.
    
    Args:
        sinr_db: SINR in dB
        throughput_mbps: Measured throughput
        theoretical_max: Pre-calculated theoretical max (optional)
    
    Returns:
        Estimated BLER percentage (0-100)
    """
    if theoretical_max is None:
        theoretical_max = calculate_theoretical_max_throughput(sinr_db)
    
    throughput_ratio = throughput_mbps / theoretical_max if theoretical_max > 0 else 0
    
    # 3GPP outer loop maintains ~10% BLER under normal conditions
    # Deviation from expected throughput indicates higher BLER
    if sinr_db > 20 and throughput_ratio > 0.9:
        # Excellent conditions
        bler = np.random.uniform(0, 3)
    elif sinr_db > 15 and throughput_ratio > 0.8:
        # Good conditions
        bler = np.random.uniform(2, 6)
    elif sinr_db > 10 and throughput_ratio > 0.6:
        # Moderate conditions
        bler = np.random.uniform(5, 10)
    elif sinr_db > 5 and throughput_ratio > 0.4:
        # Poor conditions, higher retransmissions
        bler = np.random.uniform(10, 18)
    elif sinr_db > 0:
        # Very poor, many retransmissions
        bler = np.random.uniform(15, 30)
    else:
        # Extremely poor, likely outage
        bler = np.random.uniform(25, 60)
    
    return min(bler, 100)


def estimate_mos(
    latency_ms: float,
    packet_loss_pct: float,
    codec: str = "AMR-WB"
) -> float:
    """
    Estimate Mean Opinion Score using ITU-T G.107 E-model.
    
    Reference: ITU-T Recommendation G.107 (2008) - The E-model [citation:6][citation:8]
    Implementation based on standard E-model formula:
    R = Ro - Is - Id - Ie + A
    MOS = 1 + 0.035·R + 7e-6·R·(R-60)·(100-R)
    
    Args:
        latency_ms: One-way delay in milliseconds
        packet_loss_pct: Packet loss percentage
        codec: Speech codec ('AMR-WB' or 'AMR-NB')
    
    Returns:
        MOS score between 1.0 and 4.5
    """
    # Equipment impairment factors (Ie) for different codecs
    # Reference: ITU-T G.113 Appendix I
    codec_factors = {
        'AMR-WB': 10,   # Wideband AMR at 12.65 kbps
        'AMR-NB': 15,   # Narrowband AMR at 12.2 kbps
        'G.711': 0,     # PCM (reference)
    }
    
    ie = codec_factors.get(codec, 12)
    
    # Packet loss robustness factor (Bpl) - ITU-T G.107 default is 4.3 [citation:10]
    bpl = 4.3
    
    # Calculate effective delay including jitter buffer (10 ms default)
    effective_delay = latency_ms + 10
    
    # Calculate R factor (transmission rating)
    # Ro = 93.2 (default for modern networks)
    ro = 93.2
    
    # Delay impairment (Id) - simplified from ITU-T G.107
    if effective_delay < 160:
        id_factor = effective_delay / 40
    else:
        id_factor = (effective_delay - 120) / 12
    
    # Equipment impairment including packet loss
    ie_effective = ie + (95 - ie) * (packet_loss_pct / (packet_loss_pct + bpl))
    
    # Advantage factor (A) = 0 for typical conversational use
    r_factor = ro - id_factor - ie_effective
    
    # Clamp R factor to valid range [0, 100]
    r_factor = max(0, min(100, r_factor))
    
    # Convert R factor to MOS (ITU-T G.107 Appendix B)
    if r_factor < 0:
        mos = 1.0
    else:
        mos = 1 + 0.035 * r_factor + 0.000007 * r_factor * (r_factor - 60) * (100 - r_factor)
    
    # Clamp MOS to valid range
    return max(1.0, min(4.5, mos))


def generate_operator_features(df: pd.DataFrame, bandwidth_mhz: float = 20) -> pd.DataFrame:
    """
    Generate missing operator-side features from client measurements.
    
    Args:
        df: DataFrame with columns: rsrp, sinr, rsrq, throughput_dl, throughput_ul, 
                                     latency_ms (or ping_avg)
        bandwidth_mhz: System bandwidth in MHz (default 20 for LTE)
    
    Returns:
        DataFrame with added features: prb_util_dl_pct, prb_util_ul_pct, mimo_rank, 
                                       bler_dl_pct, mos
    """
    # Make a copy to avoid modifying original
    df_result = df.copy()
    
    # Handle latency column (prefer latency_ms, fallback to ping_avg)
    if 'latency_ms' not in df_result.columns and 'ping_avg' in df_result.columns:
        df_result['latency_ms'] = df_result['ping_avg']
    elif 'latency_ms' not in df_result.columns:
        # Default latency if neither exists (conservative estimate)
        df_result['latency_ms'] = 50.0
    
    # 1. Calculate theoretical max throughput for each row
    df_result['theoretical_max_dl_mbps'] = df_result['sinr'].apply(
        lambda x: calculate_theoretical_max_throughput(x, bandwidth_mhz)
    )
    
    # 2. Estimate PRB utilization (DL)
    df_result['prb_util_dl_pct'] = df_result.apply(
        lambda row: estimate_prb_utilization(
            row['throughput_dl'], row['sinr'], bandwidth_mhz
        ),
        axis=1
    )
    
    # 3. Estimate PRB utilization (UL) - similar but typically lower capacity
    df_result['theoretical_max_ul_mbps'] = df_result['theoretical_max_dl_mbps'] * 0.3
    df_result['prb_util_ul_pct'] = df_result.apply(
        lambda row: min(100, estimate_prb_utilization(
            row['throughput_ul'], max(0, row['sinr'] - 3), bandwidth_mhz
        ) * 1.2),
        axis=1
    )
    
    # 4. Estimate MIMO rank
    df_result['mimo_rank'] = df_result.apply(
        lambda row: estimate_mimo_rank(row['sinr'], row['rsrp']),
        axis=1
    )
    
    # 5. Estimate BLER (DL)
    df_result['bler_dl_pct'] = df_result.apply(
        lambda row: estimate_bler(row['sinr'], row['throughput_dl'], row['theoretical_max_dl_mbps']),
        axis=1
    )
    
    # 6. Estimate MOS (using latency and BLER as packet loss proxy)
    # BLER approximates packet loss for voice traffic
    df_result['mos'] = df_result.apply(
        lambda row: estimate_mos(row['latency_ms'], row['bler_dl_pct']),
        axis=1
    )
    
    # 7. Clean up temporary columns
    temp_cols = ['theoretical_max_dl_mbps', 'theoretical_max_ul_mbps']
    df_result = df_result.drop(columns=temp_cols)
    
    return df_result


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    # Example usage with your existing dataset
    # Assume df is your DataFrame with required columns
    # Required columns: rsrp, sinr, rsrq, throughput_dl, throughput_ul, latency_ms
    
    # Option 1: Load from CSV
    df = pd.read_csv('qosbuddy_dataset_final.csv')
    
    # Option 2: Create sample data for testing
 

    
    # Generate features
    df_enhanced = generate_operator_features(df)
    
    # Display results
    print("Generated Features:")
    print("=" * 80)
    print(f"PRB utilization (DL): {df_enhanced['prb_util_dl_pct'].tolist()}")
    print(f"PRB utilization (UL): {df_enhanced['prb_util_ul_pct'].tolist()}")
    print(f"MIMO rank: {df_enhanced['mimo_rank'].tolist()}")
    print(f"BLER (DL): {df_enhanced['bler_dl_pct'].tolist()}")
    print(f"MOS: {df_enhanced['mos'].tolist()}")
    
    # Save enhanced dataset
    df_enhanced.to_csv('enhanced_dataset.csv', index=False)