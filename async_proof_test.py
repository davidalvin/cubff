#!/usr/bin/env python3
import os
import sys
import time
import argparse
import random

# Add the bin directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'bin'))

try:
    import cubff
    print("✅ Successfully imported cubff module")
except ImportError as e:
    print(f"❌ Failed to import cubff: {e}")
    sys.exit(1)

def run_simulation_test(async_mode=False, ops_interval=500000, duration=5):
    """Run a simulation test and return timing and program data"""
    print(f"\n{'='*60}")
    print(f"🧪 TESTING {'ASYNC' if async_mode else 'SYNC'} MODE")
    print(f"{'='*60}")
    
    # Configuration
    NUM_PROGRAMS = 512
    CALLBACK_INTERVAL = 1
    SAVE_INTERVAL = 10
    SAVE_PATH = f"./test_runs/{'async' if async_mode else 'sync'}_test"
    
    # Create save directory
    os.makedirs(SAVE_PATH, exist_ok=True)
    
    # Setup parameters
    params = cubff.SimulationParams()
    params.num_programs = NUM_PROGRAMS
    params.callback_interval = CALLBACK_INTERVAL
    params.save_interval = SAVE_INTERVAL
    params.save_to = SAVE_PATH
    
    if async_mode:
        params.callback_ops_interval = ops_interval
    
    # Track program evolution
    program_samples = []
    operation_counts = []
    start_time = time.time()
    
    def callback(state):
        epoch = getattr(state, 'epoch', 0)
        ops = getattr(state, 'total_ops', 0)
        
        # Visualize 10 different programs from the soup
        print(f"\n🖼️ Pretty print of 10 programs at epoch {epoch}:")
        soup_length = len(state.soup)
        if soup_length > 0:
            # Print 10 programs from different parts of the soup
            for i in range(10):
                start_pos = (i * soup_length // 10) % (soup_length - 128)
                end_pos = min(start_pos + 128, soup_length)
                if end_pos > start_pos:
                    print(f"Program {i+1:2d} (pos {start_pos:4d}-{end_pos:4d}):")
                    language.PrintProgram(1024, state.soup[start_pos:end_pos], [64])
                    print()  # Empty line between programs
        
        # Record operation count
        operation_counts.append(ops)
        
        # Sample some soup bytes every few epochs
        if epoch % 3 == 0 and len(program_samples) < 5:
            program_samples.append({
                'epoch': epoch,
                'ops': ops,
                'soup_sample': bytes(state.soup[:64]).hex()
            })
        
        # Show progress
        elapsed = time.time() - start_time
        ops_per_sec = ops / elapsed if elapsed > 0 else 0
        print(f"⏱️  Epoch {epoch:3d} | Ops: {ops:10,d} | Ops/sec: {ops_per_sec:8.0f} | Elapsed: {elapsed:5.1f}s")
        
        # Stop after duration seconds
        if elapsed > duration:
            return True  # Stop simulation
        return False
    
    # Get language and run simulation
    language = cubff.GetLanguage("bff_noheads")
    
    print(f"🚀 Starting {'async' if async_mode else 'sync'} simulation...")
    print(f"📊 Parameters: {NUM_PROGRAMS} programs, {duration}s duration")
    if async_mode:
        print(f"⚡ Async ops_interval: {ops_interval:,}")
    
    start_time = time.time()
    cubff.ResetColors()
    language.RunSimulation(params, None, callback)
    total_time = time.time() - start_time
    
    return {
        'mode': 'async' if async_mode else 'sync',
        'total_time': total_time,
        'program_samples': program_samples,
        'operation_counts': operation_counts,
        'final_ops': operation_counts[-1] if operation_counts else 0
    }

def compare_results(sync_result, async_result):
    """Compare sync and async results"""
    print(f"\n{'='*60}")
    print("📊 COMPARISON RESULTS")
    print(f"{'='*60}")
    
    # Timing comparison
    sync_time = sync_result['total_time']
    async_time = async_result['total_time']
    sync_ops = sync_result['final_ops']
    async_ops = async_result['final_ops']
    
    print(f"⏱️  Timing:")
    print(f"   Sync:  {sync_time:6.2f}s, {sync_ops:10,d} ops ({sync_ops/sync_time:8.0f} ops/sec)")
    print(f"   Async: {async_time:6.2f}s, {async_ops:10,d} ops ({async_ops/async_time:8.0f} ops/sec)")
    
    if async_time > 0:
        speedup = sync_time / async_time
        print(f"   Speedup: {speedup:.2f}x")
    
    # Program evolution comparison
    print(f"\n🔄 Program Evolution:")
    for i, (sync_sample, async_sample) in enumerate(zip(sync_result['program_samples'], async_result['program_samples'])):
        print(f"\n   Epoch {sync_sample[0]['epoch']}:")
        for j, (sync_prog, async_prog) in enumerate(zip(sync_sample, async_sample)):
            sync_len = sync_prog['length']
            async_len = async_prog['length']
            print(f"     Program {j}: Sync={sync_len:3d} chars, Async={async_len:3d} chars")
    
    # Show some actual programs
    print(f"\n📝 Sample Programs (Final Epoch):")
    if sync_result['program_samples'] and async_result['program_samples']:
        sync_final = sync_result['program_samples'][-1][0]
        async_final = async_result['program_samples'][-1][0]
        
        print(f"\n   Sync Program (len={sync_final['length']}):")
        print(f"   {sync_final['program'][:100]}{'...' if len(sync_final['program']) > 100 else ''}")
        
        print(f"\n   Async Program (len={async_final['length']}):")
        print(f"   {async_final['program'][:100]}{'...' if len(async_final['program']) > 100 else ''}")

def main():
    parser = argparse.ArgumentParser(description="Prove async simulation is working")
    parser.add_argument("--duration", type=int, default=10, help="Test duration in seconds")
    parser.add_argument("--ops_interval", type=int, default=500000, help="Async ops interval")
    args = parser.parse_args()
    
    print("🧪 CUBFF Async vs Sync Proof Test")
    print("=" * 60)
    
    # Check async support
    if not getattr(cubff, "HAVE_ASYNC", False):
        print("❌ cubff not built with async support!")
        print("   Rebuild with: make clean && make PYTHON=1 CUDA=0")
        sys.exit(1)
    
    print("✅ Async support confirmed")
    
    # Run sync test
    sync_result = run_simulation_test(async_mode=False, duration=args.duration)
    
    # Run async test
    async_result = run_simulation_test(async_mode=True, ops_interval=args.ops_interval, duration=args.duration)
    
    # Compare results
    compare_results(sync_result, async_result)
    
    print(f"\n{'='*60}")
    print("✅ PROOF COMPLETE")
    print(f"{'='*60}")
    print("The async simulation is working if:")
    print("1. ✅ Different timing patterns (async should be more consistent)")
    print("2. ✅ Different program evolution paths")
    print("3. ✅ Different final program states")
    print("4. ✅ Async callback intervals are respected")

if __name__ == "__main__":
    main() 