import numpy as np
import pandas as pd

def calculate_wma(series: pd.Series, length: int) -> pd.Series:
    """Calculates the Weighted Moving Average (WMA) for a given series."""
    weights = np.arange(1, length + 1)
    
    # Fast WMA calculation using convolution instead of rolling.apply for performance
    # np.convolve reverses the weights, so we don't need to flip them if we use mode='valid'
    # But to keep it as a pandas Series with same index, we use rolling.apply or a custom func.
    # We will use rolling.apply with raw=True for safety and exactness.
    def wma_func(x):
        return np.dot(x, weights) / weights.sum()
        
    return series.rolling(window=length).apply(wma_func, raw=True)

def calculate_mavilimw(df: pd.DataFrame, price_col: str = 'close', fmal: int = 3, smal: int = 5) -> pd.Series:
    """
    Calculates the MavilimW indicator by Kıvanç Özbilgiç.
    
    Parameters:
    - df: pandas DataFrame containing the price data.
    - price_col: string, name of the column to calculate on (default 'close').
    - fmal: int, first moving average length.
    - smal: int, second moving average length.
    
    Returns:
    - pandas Series containing the MavilimW values.
    """
    # Generate the Fibonacci sequence lengths
    tmal = fmal + smal   # 3 + 5 = 8
    Fmal = smal + tmal   # 5 + 8 = 13
    Ftmal = tmal + Fmal  # 8 + 13 = 21
    Smal = Fmal + Ftmal  # 13 + 21 = 34
    
    # Cascade the WMAs
    m1 = calculate_wma(df[price_col], fmal)
    m2 = calculate_wma(m1, smal)
    m3 = calculate_wma(m2, tmal)
    m4 = calculate_wma(m3, Fmal)
    m5 = calculate_wma(m4, Ftmal)
    mavw = calculate_wma(m5, Smal)
    
    return mavw
