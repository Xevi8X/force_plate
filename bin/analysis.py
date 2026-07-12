from enum import Enum

import matplotlib.pyplot as plt


class AnalysisMode(Enum):
    COUNTER_MOVEMENT_JUMP = 'Counter movement jump'
    TRIPLE_HOP_TEST = 'Triple hop test'
    DROP_JUMP = 'Drop jump'


LOAD_THRESHOLD_N = 20.0
GRAVITY_MPS2 = 9.81


def _segment_durations(times, loads_n, predicate):
    segments = []
    start_index = None

    for index, load_n in enumerate(loads_n):
        if predicate(load_n):
            if start_index is None:
                start_index = index
            continue

        if start_index is not None:
            end_index = index - 1
            segments.append((times[start_index], times[end_index]))
            start_index = None

    if start_index is not None:
        segments.append((times[start_index], times[-1]))

    durations = [end_t - start_t for start_t, end_t in segments]
    return segments, durations


def _compute_metrics(mode, times, loads_n, threshold_n):
    if mode == AnalysisMode.COUNTER_MOVEMENT_JUMP:
        _, air_gaps = _segment_durations(times, loads_n, lambda load: load < threshold_n)
        air_time_s = max(air_gaps) if air_gaps else 0.0
        initial_speed_mps = 0.5 * GRAVITY_MPS2 * air_time_s
        max_height_m = (initial_speed_mps ** 2) / (2.0 * GRAVITY_MPS2)
        return {
            'air_time_s': air_time_s,
            'initial_speed_mps': initial_speed_mps,
            'max_height_m': max_height_m,
            'threshold_n': threshold_n,
        }

    if mode == AnalysisMode.TRIPLE_HOP_TEST:
        _, contact_times = _segment_durations(times, loads_n, lambda load: load > threshold_n)
        if len(contact_times) > 2:
            contact_times = contact_times[1:-1]
        else:
            contact_times = []
        return {
            'contact_times_s': contact_times,
            'contact_count': len(contact_times),
            'threshold_n': threshold_n,
        }

    if mode == AnalysisMode.DROP_JUMP:
        first_contact_index = next(
            (idx for idx, load in enumerate(loads_n) if load > threshold_n),
            None,
        )
        if first_contact_index is None:
            return {
                'contact_time_s': 0.0,
                'threshold_n': threshold_n,
            }

        end_contact_index = len(loads_n) - 1
        for idx in range(first_contact_index + 1, len(loads_n)):
            if loads_n[idx] < threshold_n:
                end_contact_index = idx
                break

        return {
            'contact_time_s': times[end_contact_index] - times[first_contact_index],
            'threshold_n': threshold_n,
        }

    return {'threshold_n': threshold_n}


def _format_metrics(mode, metrics):
    if mode == AnalysisMode.COUNTER_MOVEMENT_JUMP:
        return (
            f"Threshold: {metrics['threshold_n']:.1f} N\n"
            f"Air time: {metrics['air_time_s']:.4f} s\n"
            f"Initial speed: {metrics['initial_speed_mps']:.4f} m/s\n"
            f"Max height: {metrics['max_height_m']:.4f} m"
        )

    if mode == AnalysisMode.TRIPLE_HOP_TEST:
        contact_items = [f'{duration:.4f}' for duration in metrics['contact_times_s']]
        contacts_text = ', '.join(contact_items) if contact_items else 'none'
        return (
            f"Threshold: {metrics['threshold_n']:.1f} N\n"
            f"Contact count: {metrics['contact_count']}\n"
            f"Contact times [s]: {contacts_text}"
        )

    if mode == AnalysisMode.DROP_JUMP:
        return (
            f"Threshold: {metrics['threshold_n']:.1f} N\n"
            f"Contact time: {metrics['contact_time_s']:.4f} s"
        )

    return f"Threshold: {metrics['threshold_n']:.1f} N"


def analyse(mode, data, show=True, threshold_n=LOAD_THRESHOLD_N):
    if not data:
        return False

    selected_mode = mode if isinstance(mode, AnalysisMode) else AnalysisMode(mode)
    times = [point[0] for point in data]
    loads_n = [point[1] for point in data]
    metrics = _compute_metrics(selected_mode, times, loads_n, threshold_n)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(times, loads_n, linewidth=1.2)
    ax.axhline(threshold_n, color='tab:red', linestyle='--', linewidth=1.0, alpha=0.8)
    ax.set_title(selected_mode.value)
    ax.set_xlabel('Time [s]')
    ax.set_ylabel('Load [N]')
    ax.grid(True, alpha=0.3)

    metrics_text = _format_metrics(selected_mode, metrics)
    ax.text(
        0.02,
        0.98,
        metrics_text,
        transform=ax.transAxes,
        va='top',
        ha='left',
        bbox={'boxstyle': 'round,pad=0.3', 'fc': 'white', 'ec': 'black', 'alpha': 0.85},
    )

    value_label = ax.annotate(
        '',
        xy=(0, 0),
        xytext=(12, 12),
        textcoords='offset points',
        bbox={'boxstyle': 'round,pad=0.3', 'fc': 'white', 'ec': 'black', 'alpha': 0.85},
    )
    value_label.set_visible(False)

    def on_move(event):
        if event.inaxes != ax or event.xdata is None:
            if value_label.get_visible():
                value_label.set_visible(False)
                fig.canvas.draw_idle()
            return

        nearest_index = min(
            range(len(times)),
            key=lambda idx: abs(times[idx] - event.xdata),
        )
        nearest_time = times[nearest_index]
        nearest_load = loads_n[nearest_index]

        value_label.xy = (nearest_time, nearest_load)
        value_label.set_text(f't={nearest_time:.4f} s\nF={nearest_load:.2f} N')
        value_label.set_visible(True)
        fig.canvas.draw_idle()

    fig.canvas.mpl_connect('motion_notify_event', on_move)
    fig.tight_layout()

    if show:
        plt.show(block=False)

    return metrics
