def trace_program_pair(state, pair_index, program_size=128):
    left = state.shuffle_idx[2 * pair_index]
    right = state.shuffle_idx[2 * pair_index + 1]
    left_prog = state.soup[left * program_size : (left + 1) * program_size]
    right_prog = state.soup[right * program_size : (right + 1) * program_size]
    left_steps = state.steps_per_prog[left]
    right_steps = state.steps_per_prog[right]

    print(f" Parents: {left} & {right}")
    print(f"  Left steps: {left_steps}")
    print(f"  Right steps: {right_steps}")
    print(f"  Left bytes:  {left_prog.hex()}")
    print(f"  Right bytes: {right_prog.hex()}")