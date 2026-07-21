import csv

import numpy as np


LOAD_THRESHOLD_N = 20.0
GRAVITY_MPS2 = 9.81

ANALYSES = {
    'Counter movement jump': 'flight_time',
    'Repeated jump test': 'contact_times',
    'Drop jump': 'contact_time',
    'Soleus isometric force': 'isometric_force',
    'Achilles isometric force': 'isometric_force',
    'Squat 90 isometric force': 'isometric_force',
    'Deadlift isometric force': 'isometric_force',
    'Pectoralis 90 isometric force': 'isometric_force',
    'Pectoralis 135 isometric force': 'isometric_force',
    'Pectoralis 180 isometric force': 'isometric_force',
}


def _segments(times, loads_n, predicate):
    segments = []
    start = None

    for index, load_n in enumerate(loads_n):
        if predicate(load_n):
            if start is None:
                start = index
        elif start is not None:
            segments.append((times[start], times[index - 1]))
            start = None

    if start is not None:
        segments.append((times[start], times[-1]))

    return segments


def _flight_time(times, loads_n, extrema_window_s=2.0, onset_ratio=0.02):
    gaps = _segments(times, loads_n, lambda load: load < LOAD_THRESHOLD_N)
    gap = max(gaps, key=lambda item: item[1] - item[0], default=None)

    if gap is None:
        return {}

    takeoff_time, landing_time = gap
    takeoff_index = next(i for i, time in enumerate(times) if time == takeoff_time)
    landing_index = next(i for i, time in enumerate(times) if time == landing_time)

    window_start = takeoff_time - extrema_window_s
    takeoff_window = [
        i for i in range(takeoff_index)
        if times[i] >= window_start
    ]

    if not takeoff_window:
        takeoff_window = list(range(takeoff_index))

    standing_loads = [
        load for time, load in zip(times, loads_n)
        if time < window_start
    ]

    if not standing_loads:
        standing_loads = loads_n[:max(1, takeoff_window[0])]

    mean_gravity_force = sum(standing_loads) / len(standing_loads)
    onset_threshold = mean_gravity_force * (1.0 - onset_ratio)

    takeoff_peak_index = max(
        takeoff_window,
        key=lambda i: loads_n[i],
    )

    eccentric_start_index = next(
        (
            i for i in takeoff_window
            if i < takeoff_peak_index and loads_n[i] < onset_threshold
        ),
        takeoff_window[0],
    )

    eccentric_min_index = min(
        range(eccentric_start_index, takeoff_peak_index + 1),
        key=lambda i: loads_n[i],
    )

    landing_window = [
        i for i in range(landing_index + 1, len(times))
        if times[i] <= landing_time + extrema_window_s
    ]

    landing_peak_index = max(
        landing_window,
        key=lambda i: loads_n[i],
        default=landing_index,
    )

    eccentric_time_s = (
        times[eccentric_min_index] - times[eccentric_start_index]
    )
    concentric_time_s = (
        times[takeoff_peak_index] - times[eccentric_min_index]
    )

    eccentric_min_force = loads_n[eccentric_min_index]
    takeoff_peak_force = loads_n[takeoff_peak_index]
    landing_peak_force = loads_n[landing_peak_index]

    eccentric_rate = (
        (eccentric_min_force - mean_gravity_force) / eccentric_time_s
        if eccentric_time_s > 0 else 0.0
    )
    concentric_rate = (
        (takeoff_peak_force - eccentric_min_force) / concentric_time_s
        if concentric_time_s > 0 else 0.0
    )

    takeoff_transition_time_s = (
        takeoff_time - times[takeoff_peak_index]
    )
    landing_transition_time_s = (
        times[landing_peak_index] - landing_time
    )

    air_time_s = landing_time - takeoff_time
    initial_speed_mps = 0.5 * GRAVITY_MPS2 * air_time_s

    return {
        'mean_gravity_force': mean_gravity_force,
        'eccentric_time_s': eccentric_time_s,
        'eccentric_min_force': eccentric_min_force,
        'eccentric_rate_of_force_nps': eccentric_rate,
        'concentric_time_s': concentric_time_s,
        'concentric_rate_of_force_nps': concentric_rate,
        'takeoff_peak_force': takeoff_peak_force,
        'takeoff_transition_time_s': takeoff_transition_time_s,
        'air_time_s': air_time_s,
        'initial_speed_mps': initial_speed_mps,
        'landing_transition_time_s': landing_transition_time_s,
        'landing_peak_force': landing_peak_force,
        'max_height_m': initial_speed_mps ** 2 / (2.0 * GRAVITY_MPS2),
    }

def _contact_times(times, loads_n):
    all_contacts = _segments(
        times,
        loads_n,
        lambda load: load > LOAD_THRESHOLD_N,
    )
    all_air_gaps = _segments(
        times,
        loads_n,
        lambda load: load < LOAD_THRESHOLD_N,
    )

    pairs = []

    for contact, next_contact in zip(
        all_contacts[1:-1],
        all_contacts[2:],
    ):
        air_gap = next(
            (
                gap for gap in all_air_gaps
                if contact[1] < gap[0]
                and gap[1] < next_contact[0]
            ),
            None,
        )

        if air_gap is not None:
            pairs.append((contact, air_gap))

    contacts = [contact for contact, _ in pairs]
    air_gaps = [air_gap for _, air_gap in pairs]

    contact_times_s = [
        end - start for start, end in contacts
    ]
    air_gap_times_s = [
        end - start for start, end in air_gaps
    ]

    contact_forces = [
        [
            load for time, load in zip(times, loads_n)
            if start <= time <= end
        ]
        for start, end in contacts
    ]

    mean_forces_n = [
        sum(forces) / len(forces)
        for forces in contact_forces
    ]

    heights_m = [
        GRAVITY_MPS2 * air_time ** 2 / 8.0
        for air_time in air_gap_times_s
    ]

    rsi_mps = [
        height / contact_time if contact_time > 0 else 0.0
        for height, contact_time in zip(
            heights_m,
            contact_times_s,
        )
    ]

    all_contact_forces = [
        force
        for forces in contact_forces
        for force in forces
    ]

    return {
        'contact_count': len(contacts),
        'contacts': contacts,
        'contact_times_s': contact_times_s,
        'air_gaps': air_gaps,
        'air_gap_times_s': air_gap_times_s,
        'mean_forces_n': mean_forces_n,
        'heights_m': heights_m,
        'rsi_mps': rsi_mps,
        'mean_contact_time_s': (
            sum(contact_times_s) / len(contact_times_s)
            if contact_times_s else 0.0
        ),
        'min_contact_time_s': min(contact_times_s, default=0.0),
        'max_contact_time_s': max(contact_times_s, default=0.0),
        'max_height_m': max(heights_m, default=0.0),
        'max_mean_force_n': max(mean_forces_n, default=0.0),
        'global_mean_force_n': (
            sum(all_contact_forces) / len(all_contact_forces)
            if all_contact_forces else 0.0
        ),
        'max_rsi_mps': max(rsi_mps, default=0.0),
    }


def _contact_time(times, loads_n):
    contacts = _segments(
        times,
        loads_n,
        lambda load: load > LOAD_THRESHOLD_N,
    )
    air_gaps = _segments(
        times,
        loads_n,
        lambda load: load < LOAD_THRESHOLD_N,
    )

    if not contacts:
        return {
            'contact_time_s': 0.0,
            'air_time_s': 0.0,
            'takeoff_peak_force_n': 0.0,
            'landing_peak_force_n': 0.0,
            'mean_contact_force_n': 0.0,
            'jump_height_m': 0.0,
            'rsi_mps': 0.0,
        }

    contact = contacts[0]
    contact_start, contact_end = contact

    air_gap = next(
        (
            gap for gap in air_gaps
            if gap[0] > contact_end
        ),
        None,
    )

    landing_contact = next(
        (
            item for item in contacts[1:]
            if air_gap is not None and item[0] > air_gap[1]
        ),
        None,
    )

    contact_forces = [
        load for time, load in zip(times, loads_n)
        if contact_start <= time <= contact_end
    ]

    landing_forces = (
        [
            load for time, load in zip(times, loads_n)
            if landing_contact[0] <= time <= landing_contact[1]
        ]
        if landing_contact is not None else []
    )

    contact_time_s = contact_end - contact_start
    air_time_s = (
        air_gap[1] - air_gap[0]
        if air_gap is not None else 0.0
    )
    jump_height_m = GRAVITY_MPS2 * air_time_s ** 2 / 8.0

    return {
        'contact_time_s': contact_time_s,
        'air_time_s': air_time_s,
        'takeoff_peak_force_n': max(contact_forces, default=0.0),
        'landing_peak_force_n': max(landing_forces, default=0.0),
        'mean_contact_force_n': (
            sum(contact_forces) / len(contact_forces)
            if contact_forces else 0.0
        ),
        'jump_height_m': jump_height_m,
        'rsi_mps': (
            jump_height_m / contact_time_s
            if contact_time_s > 0 else 0.0
        ),
    }

def _isometric_force(times, loads_n):
    if not times:
        return {
            'increased_force_time_s': 0.0,
            'mean_increased_force_n': 0.0,
        }

    loads = np.asarray(loads_n, dtype=float)

    if np.ptp(loads) == 0:
        return {
            'increased_force_time_s': 0.0,
            'mean_increased_force_n': float(loads[0]),
        }

    histogram, edges = np.histogram(loads, bins='auto')
    centers = (edges[:-1] + edges[1:]) / 2.0

    low_count = np.cumsum(histogram)
    high_count = histogram.sum() - low_count

    weighted_sum = np.cumsum(histogram * centers)
    total_sum = weighted_sum[-1]

    low_mean = weighted_sum / np.maximum(low_count, 1)
    high_mean = (
        total_sum - weighted_sum
    ) / np.maximum(high_count, 1)

    score = (
        low_count
        * high_count
        * (low_mean - high_mean) ** 2
    )
    score[(low_count == 0) | (high_count == 0)] = 0

    threshold = edges[np.argmax(score) + 1]

    increased_segments = _segments(
        times,
        loads_n,
        lambda force: force > threshold,
    )
    increased_segment = max(
        increased_segments,
        key=lambda segment: segment[1] - segment[0],
        default=None,
    )

    if increased_segment is None:
        return {
            'increased_force_time_s': 0.0,
            'mean_increased_force_n': 0.0,
        }

    start, end = increased_segment
    increased_indices = [
        index
        for index, time in enumerate(times)
        if start <= time <= end
    ]

    max_index = max(
        increased_indices,
        key=lambda index: loads_n[index],
    )
    max_force_time_s = times[max_index]
    increased_time_s = end - start

    return {
        'start_time_s': start,
        'end_time_s': end,
        'force_time_s': increased_time_s,
        'mean_force_n': (
            sum(loads_n[index] for index in increased_indices)
            / len(increased_indices)
        ),
        'max_force_n': loads_n[max_index],
        'max_force_ratio': (
            (max_force_time_s - start) / increased_time_s
            if increased_time_s > 0 else 0.0
        ),
    }

ALGORITHMS = {
    'flight_time': _flight_time,
    'contact_times': _contact_times,
    'contact_time': _contact_time,
    'isometric_force': _isometric_force,
}


def algorithm_for(test_name):
    return ANALYSES[test_name]


def analyse(test_name, data, algorithm=None):
    if not data:
        return None

    algorithm = algorithm or algorithm_for(test_name)
    times, loads_n = zip(*data)
    return ALGORITHMS[algorithm](times, loads_n)


def _format_metrics(algorithm, metrics):
    if algorithm == 'flight_time':
        return (
            f"Mean gravity force: {metrics['mean_gravity_force']:.2f} N\n"
            f"Eccentric time: {metrics['eccentric_time_s']:.4f} s\n"
            f"Eccentric min force: {metrics['eccentric_min_force']:.2f} N\n"
            f"Eccentric rate of force: {metrics['eccentric_rate_of_force_nps']:.2f} N/s\n"
            f"Concentric time: {metrics['concentric_time_s']:.4f} s\n"
            f"Concentric rate of force: {metrics['concentric_rate_of_force_nps']:.2f} N/s\n"
            f"Takeoff peak force: {metrics['takeoff_peak_force']:.2f} N\n"
            f"Initial speed: {metrics['initial_speed_mps']:.4f} m/s\n"
            f"Air time: {metrics['air_time_s']:.4f} s\n"
            f"Landing peak force: {metrics['landing_peak_force']:.2f} N"
            f"Max height: {metrics['max_height_m']:.4f} m\n"
        )

    if algorithm == 'contact_times':
        contact_times = ', '.join(
            f'{value:.4f}' for value in metrics['contact_times_s']
        ) or 'none'
        air_gaps = ', '.join(
            f'{value:.4f}' for value in metrics['air_gap_times_s']
        ) or 'none'
        mean_forces = ', '.join(
            f'{value:.2f}' for value in metrics['mean_forces_n']
        ) or 'none'
        heights = ', '.join(
            f'{value:.4f}' for value in metrics['heights_m']
        ) or 'none'
        rsi = ', '.join(
            f'{value:.4f}' for value in metrics['rsi_mps']
        ) or 'none'

        return (
            f"Contact count: {metrics['contact_count']}\n"
            f"Contact times [s]: {contact_times}\n"
            f"Air gaps [s]: {air_gaps}\n"
            f"Mean forces [N]: {mean_forces}\n"
            f"Heights [m]: {heights}\n"
            f"RSI [m/s]: {rsi}\n"
            f"Mean contact time: {metrics['mean_contact_time_s']:.4f} s\n"
            f"Minimum contact time: {metrics['min_contact_time_s']:.4f} s\n"
            f"Maximum contact time: {metrics['max_contact_time_s']:.4f} s\n"
            f"Maximum height: {metrics['max_height_m']:.4f} m\n"
            f"Maximum mean force: {metrics['max_mean_force_n']:.2f} N\n"
            f"Global mean contact force: {metrics['global_mean_force_n']:.2f} N"
            f"Maximum RSI: {metrics['max_rsi_mps']:.4f} m/s"
        )
    
    if algorithm == 'contact_time':
        return (
            f"Contact time: {metrics['contact_time_s']:.4f} s\n"
            f"Air time: {metrics['air_time_s']:.4f} s\n"
            f"Takeoff peak force: {metrics['takeoff_peak_force_n']:.2f} N\n"
            f"Landing peak force: {metrics['landing_peak_force_n']:.2f} N\n"
            f"Mean contact force: {metrics['mean_contact_force_n']:.2f} N\n"
            f"Jump height: {metrics['jump_height_m']:.4f} m\n"
            f"RSI: {metrics['rsi_mps']:.4f} m/s"
        )
    
    if algorithm == 'isometric_force':
        return (
            f"Start time: {metrics['start_time_s']:.4f} s\n"
            f"End time: {metrics['end_time_s']:.4f} s\n"
            f"Force time: {metrics['force_time_s']:.4f} s\n"
            f"Mean force: {metrics['mean_force_n']:.2f} N\n"
            f"Max force: {metrics['max_force_n']:.2f} N\n"
            f"Max force ratio: {metrics['max_force_ratio']:.4f}"
        )

    return ()


def plot_analysis(figure, test_name, data, algorithm=None):
    algorithm = algorithm or algorithm_for(test_name)
    metrics = analyse(test_name, data, algorithm)
    if metrics is None:
        return None

    old_callback = getattr(figure, '_analysis_motion_callback', None)
    if old_callback is not None:
        figure.canvas.mpl_disconnect(old_callback)

    times, loads_n = zip(*data)
    figure.clear()
    ax = figure.add_subplot(111)
    ax.plot(times, loads_n, linewidth=1.2)
    ax.set_title(test_name)
    ax.set_xlabel('Time [s]')
    ax.set_ylabel('Load [N]')
    ax.grid(True, alpha=0.3)
    ax.text(
        0.02,
        0.98,
        _format_metrics(algorithm, metrics),
        transform=ax.transAxes,
        va='top',
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
                figure.canvas.draw_idle()
            return

        index = min(range(len(times)), key=lambda item: abs(times[item] - event.xdata))
        value_label.xy = (times[index], loads_n[index])
        value_label.set_text(f't={times[index]:.4f} s\nF={loads_n[index]:.2f} N')
        value_label.set_visible(True)
        figure.canvas.draw_idle()

    figure._analysis_motion_callback = figure.canvas.mpl_connect('motion_notify_event', on_move)
    figure.tight_layout()
    figure.canvas.draw_idle()
    return metrics


def append_summary(folder_path, data_path, test_name, metrics):
    header = ['test_name']
    header.extend(metrics.keys())
    safe_test_name = ''.join(
        char.lower() if char.isalnum() else '_'
        for char in test_name
    ).strip('_')
    file_path = folder_path / f'{safe_test_name}.csv'
    write_header = not file_path.exists()

    with file_path.open('a', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=header)
        if write_header:
            writer.writeheader()
        writer.writerow({
            'test_name': data_path.stem,
            **metrics,
        })


def load_log(file_path):
    metadata = {}
    data = []

    with open(file_path, newline='') as file:
        lines = []
        for line in file:
            if line.startswith('#'):
                key, separator, value = line[1:].partition(':')
                if separator:
                    metadata[key.strip()] = value.strip()
            elif line.strip():
                lines.append(line)

    for row in csv.reader(lines):
        if len(row) != 2:
            continue
        try:
            data.append((float(row[0]), float(row[1])))
        except ValueError:
            continue

    return metadata, data
