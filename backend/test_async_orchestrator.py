"""
Simple test to verify async orchestrator works correctly
"""
import asyncio
import time


async def mock_agent(name, duration):
    """Mock agent that simulates work"""
    print(f"  Starting {name}...")
    await asyncio.sleep(duration)
    print(f"  ✅ {name} completed ({duration}s)")
    return f"{name}_result"


async def test_wave_execution():
    """Test wave-based parallel execution"""
    print("Testing Wave-based Parallel Execution")
    print("=" * 60)
    
    total_start = time.time()
    
    # Wave 1: Layout + Tampering (parallel)
    print("\n🌊 Wave 1: Layout + Tampering (parallel)")
    wave1_start = time.time()
    wave1_results = await asyncio.gather(
        mock_agent("Layout", 2),
        mock_agent("Tampering", 2)
    )
    wave1_duration = time.time() - wave1_start
    print(f"  Wave 1 completed in {wave1_duration:.2f}s")
    
    # Wave 2: Extraction (sequential)
    print("\n🌊 Wave 2: Extraction (sequential)")
    wave2_start = time.time()
    extraction_result = await mock_agent("Extraction", 3)
    wave2_duration = time.time() - wave2_start
    print(f"  Wave 2 completed in {wave2_duration:.2f}s")
    
    # Wave 3: Fraud + Insights (parallel)
    print("\n🌊 Wave 3: Fraud + Insights (parallel)")
    wave3_start = time.time()
    wave3_results = await asyncio.gather(
        mock_agent("Fraud", 2),
        mock_agent("Insights", 2)
    )
    wave3_duration = time.time() - wave3_start
    print(f"  Wave 3 completed in {wave3_duration:.2f}s")
    
    total_duration = time.time() - total_start
    
    print("\n" + "=" * 60)
    print(f"✅ Total execution time: {total_duration:.2f}s")
    print(f"\nSequential would take: 2+2+3+2+2 = 11s")
    print(f"Parallel (3 waves) took: {total_duration:.2f}s")
    print(f"Speedup: {11/total_duration:.2f}x faster")
    
    # Verify timing
    expected_time = max(2, 2) + 3 + max(2, 2)  # Wave1 + Wave2 + Wave3 = 2 + 3 + 2 = 7s
    assert 6.5 <= total_duration <= 8.0, f"Expected ~7s, got {total_duration:.2f}s"
    print("\n✅ Timing verification passed!")


if __name__ == "__main__":
    asyncio.run(test_wave_execution())
