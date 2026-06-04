import numpy as np
import pandas as pd
import warnings
from hmmlearn.hmm import GaussianHMM
from hurst import compute_Hc

warnings.filterwarnings("ignore")

def compute_shannon_entropy(series, window=20):
    """Calculates Shannon Entropy of rolling window returns. High entropy = noise/whipsaw."""
    def entropy(x):
        # Discretize returns into 10 bins
        hist, _ = np.histogram(x, bins=10, density=True)
        hist = hist[hist > 0]
        return -np.sum(hist * np.log2(hist))
    
    return series.rolling(window).apply(entropy, raw=True)

def compute_fractal_dimension(high, low, close, window=20):
    """Calculates Fractal Dimension (Choppiness Index proxy). Higher = more ranging/choppy."""
    tr = np.maximum(high - low, np.maximum(np.abs(high - close.shift(1)), np.abs(low - close.shift(1))))
    atr = tr.rolling(window).sum()
    max_hi = high.rolling(window).max()
    min_lo = low.rolling(window).min()
    
    # Choppiness Index formula
    chop = 100 * np.log10(atr / (max_hi - min_lo)) / np.log10(window)
    return chop

def compute_advanced_features(df):
    """Add advanced mean-reverting/noise features for Forex to the dataframe."""
    df = df.copy()
    
    # Log Returns
    df['log_ret'] = np.log(df['close'] / df['close'].shift(1))
    
    # Volatility
    df['volatility_20'] = df['log_ret'].rolling(20).std() * np.sqrt(252 * 6) # 4H annualized approx
    
    # Shannon Entropy
    df['entropy_20'] = compute_shannon_entropy(df['log_ret'], window=20)
    
    # Fractal Dimension (Choppiness)
    df['chop_20'] = compute_fractal_dimension(df['high'], df['low'], df['close'], window=20)
    
    # Hurst Exponent (rolling 60 periods ~ 10 days in 4H)
    def rolling_hurst(x):
        if len(x) < 60: return np.nan
        try:
            H, c, data = compute_Hc(x, kind='price', simplified=True)
            return H
        except:
            return np.nan
    
    # Warning: Rolling hurst is slow. We use a step or approximation if needed.
    # For now, we'll calculate it for the whole series to avoid massive slow down in Pandas rolling
    # A more efficient approach is to only compute Hurst for the training set overall or use a fast cython version.
    # We will skip rolling hurst for the live loop to ensure speed, and use chop & entropy instead.
    
    return df.dropna()

def train_hmm_regimes(df, n_components=2):
    """Trains a Gaussian HMM on Log Returns and Volatility to identify hidden market states."""
    # We use log_ret and volatility as observed variables
    data = df[['log_ret', 'volatility_20']].dropna().values
    
    # Train HMM
    model = GaussianHMM(n_components=n_components, covariance_type="full", n_iter=100, random_state=42)
    model.fit(data)
    
    # Predict hidden states
    hidden_states = model.predict(data)
    
    # Determine which state is "Volatile/Whipsaw" vs "Calm/Trending"
    # Usually the state with higher variance in log_ret is the volatile one.
    variances = [np.var(data[hidden_states == i, 0]) for i in range(n_components)]
    volatile_state = np.argmax(variances)
    calm_state = np.argmin(variances)
    
    return model, hidden_states, volatile_state, calm_state

def predict_hmm_regime(model, recent_data):
    """Predict the regime for the latest data points."""
    data = recent_data[['log_ret', 'volatility_20']].dropna().values
    # Predict returns the state sequence, we care about the last one
    if len(data) == 0:
        return -1
    states = model.predict(data)
    return states[-1]
