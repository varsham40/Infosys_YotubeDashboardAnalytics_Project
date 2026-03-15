import pandas as pd
import numpy as np
import pytest
import sys
import os

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database_operations.Metrics_caluclator import (
    Caluclate_engagement_rate,
    Calculate_sub_to_view_ratio,
    benchmark_videos
)

def test_calculate_engagement_rate():
    data = {
        'view_count': [1000, 2000, 0],
        'like_count': [50, 100, 0],
        'comment_count': [10, 20, 0]
    }
    df = pd.DataFrame(data)
    result_df = Caluclate_engagement_rate(df)
    
    # (60 / 1000) * 100 = 6.0
    assert result_df['engagement_rate'].iloc[0] == 6.0
    # (120 / 2000) * 100 = 6.0
    assert result_df['engagement_rate'].iloc[1] == 6.0
    # Division by zero should be 0
    assert result_df['engagement_rate'].iloc[2] == 0.0

def test_calculate_sub_to_view_ratio():
    data = {
        'view_count': [100, 500, 1000],
        'subscribers': [10, 50, 0]
    }
    df = pd.DataFrame(data)
    result_df = Calculate_sub_to_view_ratio(df)
    
    assert result_df['sub_to_view_ratio'].iloc[0] == 10.0
    assert result_df['sub_to_view_ratio'].iloc[1] == 10.0
    assert result_df['sub_to_view_ratio'].iloc[2] == 0.0

def test_benchmark_videos():
    data = {
        'view_count': [100, 200, 300] # Mean = 200
    }
    df = pd.DataFrame(data)
    result_df = benchmark_videos(df)
    
    # 100 / 200 = 0.5 (Below Average < 0.8)
    assert result_df['performance_rank'].iloc[0] == 'Below Average'
    # 200 / 200 = 1.0 (Average 0.8 to 1.2)
    assert result_df['performance_rank'].iloc[1] == 'Average'
    # 300 / 200 = 1.5 (High Performer > 1.2)
    assert result_df['performance_rank'].iloc[2] == 'High Performer'
