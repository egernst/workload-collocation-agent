# Copyright (c) 2018 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import os
from io import BytesIO
from unittest import mock
from unittest.mock import Mock, patch

import pytest

from wca import metrics
from wca import perf
from wca import perf_const as pc
from wca.metrics import MetricName, DerivedMetricName, DerivedMetricsGenerator
from wca.perf import _parse_raw_event_name
from tests.testing import create_open_mock


@pytest.mark.parametrize("raw_value,time_enabled,time_running,expected_value,expected_factor", [
    (300, 200, 100, 600, 2.0),
    (0, 0, 0, 0, 0),
    (200, 0, 100, 0, 0),
    (200, 100, 0, 0, 0),
    (300, 200, 200, 300, 1.0),
])
def test_scale_counter_value(raw_value, time_running, time_enabled, expected_value,
                             expected_factor):
    assert perf._scale_counter_value(raw_value, time_enabled, time_running) == (
        expected_value, expected_factor)


@patch('os.open', return_value=10)
def test_get_cgroup_fd(os_open):
    assert perf._get_cgroup_fd('a_cgroup') == 10
    os_open.assert_called_once_with('/sys/fs/cgroup/perf_event/a_cgroup',
                                    os.O_RDONLY)


@patch('os.fdopen', return_value=object)
def test_create_file_from_valid_fd(_):
    file = perf._create_file_from_fd(1)
    assert file is not None


def test_create_file_from_invalid_fd():
    with pytest.raises(perf.UnableToOpenPerfEvents):
        perf._create_file_from_fd(-1)


@pytest.mark.parametrize("disabled_flag,expected", [
    (True, pc.AttrFlags.exclude_guest | pc.AttrFlags.disabled),
    (False, pc.AttrFlags.exclude_guest)
])
def test_create_event_attributes_disabled_flag(disabled_flag, expected):
    assert perf._create_event_attributes(
        metrics.MetricName.CYCLES, disabled_flag).flags == expected


@pytest.mark.parametrize("raw_string,expected", [
    ('0-31', list(range(32))),
    ('0', [0]),
    ('0-3,6,10-12', [0, 1, 2, 3, 6, 10, 11, 12])
])
def test_parse_online_cpus_string(raw_string, expected):
    assert perf._parse_online_cpus_string(raw_string) == expected


@pytest.mark.parametrize("file,event_names,expected", [
    (BytesIO(b"\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
             b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x4a\x16\x00\x00\x00\x00\x00\x00"),
     [metrics.MetricName.CYCLES],
     {metrics.MetricName.CYCLES: 0,
      metrics.MetricName.SCALING_FACTOR_AVG: 0,
      metrics.MetricName.SCALING_FACTOR_MAX: 0}
     ),
    # case with no scaling
    (BytesIO(b"\x03\x00\x00\x00\x00\x00\x00\x00\x26\xe7\xea\x29\x01\x00\x00\x00\x26\xe7\xea\x29"
             b"\x01\x00\x00\x00\xa6\x6e\x1a\x9d\x08\x00\x00\x00\x1d\x17\x00\x00\x00\x00\x00\x00"
             b"\xc8\xfd\x08\x88\x04\x00\x00\x00\x1e\x17\x00\x00\x00\x00\x00\x00\x18\xc8\x43\x00"
             b"\x00\x00\x00\x00\x1f\x17\x00\x00\x00\x00\x00\x00"),
     [metrics.MetricName.INSTRUCTIONS, metrics.MetricName.CYCLES, metrics.MetricName.CACHE_MISSES],
     {metrics.MetricName.INSTRUCTIONS: 36995493542, metrics.MetricName.CYCLES: 19462159816,
      metrics.MetricName.CACHE_MISSES: 4442136,
      metrics.MetricName.SCALING_FACTOR_AVG: 1.0,
      metrics.MetricName.SCALING_FACTOR_MAX: 1.0}
     ),
    # case with 50% scaling factor
    (BytesIO(b"\x03\x00\x00\x00\x00\x00\x00\x00\xb2\xef\xff\x29\x01\x00\x00\x00\x07\x13\x08\x95"
             b"\x00\x00\x00\x00\x86\xb2\xf1\x4b\x04\x00\x00\x00\x5d\x19\x00\x00\x00\x00\x00\x00"
             b"\xbe\x74\x5f\x43\x02\x00\x00\x00\x5e\x19\x00\x00\x00\x00\x00\x00\xf0\xa5\x15\x00"
             b"\x00\x00\x00\x00\x5f\x19\x00\x00\x00\x00\x00\x00"),
     [metrics.MetricName.INSTRUCTIONS, metrics.MetricName.CYCLES, metrics.MetricName.CACHE_MISSES],
     {metrics.MetricName.INSTRUCTIONS: 36900158682, metrics.MetricName.CYCLES: 19436397211,
      metrics.MetricName.CACHE_MISSES: 2836869,
      # TODO: assert for 2.0 with some margin
      metrics.MetricName.SCALING_FACTOR_AVG: 1.9995750600302817,
      metrics.MetricName.SCALING_FACTOR_MAX: 1.9995750600302817}
     )
])
def test_parse_event_groups(file, event_names, expected):
    assert perf._parse_event_groups(file, event_names) == expected


@pytest.mark.parametrize("measurements_per_cpu,event_names,expected", [
    (
            {
                0: {
                    metrics.MetricName.CYCLES: 600,
                    metrics.MetricName.INSTRUCTIONS: 400,
                    metrics.MetricName.SCALING_FACTOR_AVG: 1.5,
                    metrics.MetricName.SCALING_FACTOR_MAX: 2.0,
                },
                1: {
                    metrics.MetricName.CYCLES: 500,
                    metrics.MetricName.INSTRUCTIONS: 300,
                    metrics.MetricName.SCALING_FACTOR_AVG: 1.0,
                    metrics.MetricName.SCALING_FACTOR_MAX: 1.0,
                }
            },
            [metrics.MetricName.CYCLES, metrics.MetricName.INSTRUCTIONS],
            {
                metrics.MetricName.CYCLES: 1100,
                metrics.MetricName.INSTRUCTIONS: 700,
                metrics.MetricName.SCALING_FACTOR_AVG: 1.25,
                metrics.MetricName.SCALING_FACTOR_MAX: 2.0,
            }
    ),
])
def test_aggregate_measurements(measurements_per_cpu, event_names, expected):
    assert perf._aggregate_measurements(measurements_per_cpu, event_names) == expected


@patch('wca.perf._get_cgroup_fd')
@patch('wca.perf.PerfCounters._open')
def test_perf_counters_init(_open_mock, _get_cgroup_fd_mock):
    prf = perf.PerfCounters('/mycgroup', [metrics.MetricName.CYCLES])
    assert prf._group_event_leader_files == {}
    _get_cgroup_fd_mock.assert_called_once()
    _open_mock.assert_called_once()


@patch('builtins.open')
@patch('wca.perf._parse_online_cpus_string', return_value=[0])
def test_get_online_cpus(_parse_online_cpu_string_mock, open_mock):
    assert perf._get_online_cpus() == [0]
    open_mock.assert_called_with('/sys/devices/system/cpu/online', 'r')


@patch('wca.perf._get_cgroup_fd')
@patch('wca.perf.PerfCounters._open')
def test_read_metrics(_open_mock, _get_cgroup_fd_mock):
    prf = perf.PerfCounters('/mycgroup', [metrics.MetricName.CYCLES])
    assert prf.get_measurements() == {metrics.MetricName.CYCLES: 0,
                                      metrics.MetricName.SCALING_FACTOR_AVG: 0,
                                      metrics.MetricName.SCALING_FACTOR_MAX: 0}


@patch('wca.perf.LIBC.ioctl', return_value=1)
@patch('wca.perf._get_cgroup_fd')
@patch('wca.perf.PerfCounters._open')
def test_reset_and_enable_group_event_leaders(_open_mock, _get_cgroup_fd_mock, ioctl_mock):
    prf = perf.PerfCounters('/mycgroup', [metrics.MetricName.CYCLES])
    # cpu0 group event leader mock
    prf._group_event_leader_files = {0: Mock()}
    prf._reset_and_enable_group_event_leaders()
    ioctl_mock.assert_has_calls([mock.ANY] * 2)


@patch('wca.perf.LIBC.ioctl', return_value=-1)
@patch('wca.perf._get_cgroup_fd')
@patch('wca.perf.PerfCounters._open')
def test_reset_and_enable_group_event_leaders_reset_fail(
        _open_mock, _get_cgroup_fd_mock, ioctl_mock
):
    prf = perf.PerfCounters('/mycgroup', [metrics.MetricName.CYCLES])
    # cpu0 group event leader mock
    prf._group_event_leader_files = {0: Mock()}
    with pytest.raises(OSError, match="Cannot reset perf counts"):
        prf._reset_and_enable_group_event_leaders()


@patch('wca.perf.LIBC.ioctl', side_effect=[1, -1])
@patch('wca.perf._get_cgroup_fd')
@patch('wca.perf.PerfCounters._open')
def test_reset_and_enable_group_event_leaders_enable_fail(
        _open_mock, _get_cgroup_fd_mock, ioctl_mock
):
    prf = perf.PerfCounters('/mycgroup', [metrics.MetricName.CYCLES])
    # cpu0 group event leader mock
    prf._group_event_leader_files = {0: Mock()}
    with pytest.raises(OSError, match="Cannot enable perf counts"):
        prf._reset_and_enable_group_event_leaders()


@patch('os.close')
@patch('wca.perf._get_cgroup_fd', return_value=10)
@patch('wca.perf.PerfCounters._open')
def test_cleanup(_open_mock, _get_cgroup_fd_mock, os_close_mock):
    prf = perf.PerfCounters('/mycgroup', [metrics.MetricName.CYCLES])
    file_descriptor_mock = Mock()
    file_descriptor_mock.close = Mock()
    prf._group_event_leader_files = {'mock1': file_descriptor_mock, 'mock2': file_descriptor_mock}
    prf._event_files = [file_descriptor_mock] * 3
    prf.cleanup()
    os_close_mock.assert_called_once_with(10)
    file_descriptor_mock.close.assert_has_calls(
        [mock.call()] * (len(prf._event_files)
                         + len(prf._group_event_leader_files)))


@patch('wca.perf._get_cgroup_fd', return_value=10)
@patch('wca.perf.PerfCounters._open')
def test_open_for_cpu_wrong_arg(_open_mock, _get_cgroup_fd_mock):
    prf = perf.PerfCounters('/mycgroup', [])
    # let's check non-existent type of measurement
    with pytest.raises(Exception, match='unknown event name'):
        prf._open_for_cpu(0, 'invalid_event_name')


@patch('os.fdopen')
@patch('wca.perf._perf_event_open', return_value=5)
@patch('wca.perf._get_cgroup_fd', return_value=10)
@patch('wca.perf.PerfCounters._open')
def test_open_for_cpu(_open_mock, _get_cgroup_fd_mock,
                      _perf_event_open_mock, fdopen_mock):
    prf = perf.PerfCounters('/mycgroup', [metrics.MetricName.CYCLES])
    prf._open_for_cpu(0, metrics.MetricName.CYCLES)
    assert prf._group_event_leader_files == {0: mock.ANY}
    assert prf._event_files == []
    # perf_event_open call for the event group leader
    _perf_event_open_mock.assert_called_once_with(
        perf_event_attr=mock.ANY,
        pid=10,
        cpu=0,
        group_fd=-1,
        flags=pc.PERF_FLAG_PID_CGROUP | pc.PERF_FLAG_FD_CLOEXEC
    )
    fdopen_mock.assert_called_once_with(5, 'rb')


@patch('os.fdopen', side_effect=[Mock(fileno=Mock(return_value=5)),
                                 Mock(fileno=Mock(return_value=6))])
@patch('wca.perf._perf_event_open', return_value=5)
@patch('wca.perf._get_cgroup_fd', return_value=10)
@patch('wca.perf.PerfCounters._open')
def test_open_for_cpu_with_existing_event_group_leader(_open_mock,
                                                       _get_cgroup_fd_mock,
                                                       _perf_event_open_mock, fdopen_mock):
    prf = perf.PerfCounters('/mycgroup', [metrics.MetricName.CYCLES])
    # Create event group leader
    prf._open_for_cpu(0, metrics.MetricName.CYCLES)
    # Create non leading event
    prf._open_for_cpu(0, metrics.MetricName.INSTRUCTIONS)
    assert prf._group_event_leader_files[0].fileno() == 5
    assert prf._event_files[0].fileno() == 6
    # perf_event_open call for non leading event
    _perf_event_open_mock.assert_called_with(perf_event_attr=mock.ANY,
                                             pid=-1,
                                             cpu=0,
                                             group_fd=5,
                                             flags=pc.PERF_FLAG_FD_CLOEXEC)


@patch('wca.perf._get_cgroup_fd')
@patch('wca.perf.PerfCounters._open')
def test_read_events_zero_values_zero_cpus(_open_mock, _get_cgroup_fd_mock):
    prf = perf.PerfCounters('/mycgroup', [])
    prf._group_event_leaders = {}
    assert prf._read_events() == {}


@patch('wca.perf._get_cgroup_fd')
@patch('wca.perf.PerfCounters._open')
def test_read_events_zero_values_one_cpu(_open_mock, _get_cgroup_fd_mock):
    prf = perf.PerfCounters('/mycgroup', [])
    # File descriptor mock for single cpu
    prf._group_event_leaders = {0: Mock()}
    assert prf._read_events() == {}


@patch('wca.perf.SetEffectiveRootUid')
@patch('os.path.exists', Mock(return_value=True))
@patch('builtins.open', new=create_open_mock({
    "/dev/cpu/0/cpuid": b"\x16\x00\x00\x00\x47\x65\x6e\x75\x6e\x74\x65\x6c\x69\x6e\x65\x49"
                        b"\x54\x06\x05\x00\x00\x08\x40\x00\xff\xfb\xfe\x7f\xff\xfb\xeb\xbf"
}))
def test_read_skylake_cpu_model(*args):
    assert pc.CPUModel.SKYLAKE == perf._get_cpu_model()


@patch('wca.perf.SetEffectiveRootUid')
@patch('os.path.exists', Mock(return_value=True))
@patch('builtins.open', new=create_open_mock({
    "/dev/cpu/0/cpuid": b"\x14\x00\x00\x00\x47\x65\x6e\x75\x6e\x74\x65\x6c\x69\x6e\x65\x49"
                        b"\xf1\x06\x04\x00\x00\x08\x20\x00\xff\xfb\xfe\x7f\xff\xfb\xeb\xbf"
}))
def test_read_broadwell_cpu_model(*args):
    assert pc.CPUModel.BROADWELL == perf._get_cpu_model()


@patch('wca.perf.SetEffectiveRootUid')
@patch('os.path.exists', Mock(return_value=True))
@patch('builtins.open', new=create_open_mock({
    "/dev/cpu/0/cpuid": b"\x0b\x00\x00\x00\x47\x65\x6e\x75\x6e\x74\x65\x6c\x69\x6e\x65\x49"
                        b"\xe5\x06\x01\x00\x00\x08\x10\x00\xfd\xe3\x98\x00\xff\xfb\xeb\xbf"
}))
def test_read_unknown_cpu_model(*args):
    assert pc.CPUModel.UNKNOWN == perf._get_cpu_model()


@pytest.mark.parametrize('event_name, expected_attr_config', [
    ('some__r000000', 0),
    ('some__r000001', 0x01000000),
    ('some__r0000ff', 0xff000000),
    ('some__r0302', 0x00000203),
    ('some__r0302ff', 0xff000203),
    ('some__rc000', 0x000000c0),  # example of Instruction Retired

])
def test_parse_raw_event_name(event_name, expected_attr_config):
    got_attr_config = _parse_raw_event_name(event_name)
    assert got_attr_config == expected_attr_config


@pytest.mark.parametrize('event_name, expected_match', [
    ('som', 'contain'),
    ('some__r00000100', 'length'),
    ('some__r0000xx', 'invalid literal'),
    ('some__rxx02', 'invalid literal'),

])
def test_parse_raw_event_name_invalid(event_name, expected_match):
    with pytest.raises(Exception, match=expected_match):
        _parse_raw_event_name(event_name)


def test_derived_metrics():
    def gm_func():
        return {
            MetricName.INSTRUCTIONS: 1000,
            MetricName.CYCLES: 5,
            MetricName.CACHE_MISSES: 10000,
            MetricName.CACHE_REFERENCES: 50000,
        }

    derived_metrics_generator = DerivedMetricsGenerator(
        event_names=[MetricName.INSTRUCTIONS, MetricName.CYCLES,
                     MetricName.CACHE_MISSES, MetricName.CACHE_REFERENCES],
        get_measurements_func=gm_func)

    # First run, does not have enough information to generate those metrics.

    with patch('time.time', return_value=1):
        measurements = derived_metrics_generator.get_measurements()
    assert DerivedMetricName.IPC not in measurements
    assert DerivedMetricName.IPS not in measurements
    assert DerivedMetricName.CACHE_HIT_RATIO not in measurements
    assert DerivedMetricName.CACHE_MISSES_PER_KILO_INSTRUCTIONS not in measurements

    # 5 seconds later
    def gm_func_2():
        return {
            MetricName.INSTRUCTIONS: 11000,  # 10k more
            MetricName.CYCLES: 15,  # 10 more
            MetricName.CACHE_MISSES: 20000,  # 10k more
            MetricName.CACHE_REFERENCES: 100000,  # 50k more
        }

    derived_metrics_generator.get_measurements_func = gm_func_2
    with patch('time.time', return_value=6):
        measurements = derived_metrics_generator.get_measurements()
    assert DerivedMetricName.IPC in measurements
    assert DerivedMetricName.IPS in measurements
    assert DerivedMetricName.CACHE_HIT_RATIO in measurements
    assert DerivedMetricName.CACHE_MISSES_PER_KILO_INSTRUCTIONS in measurements

    assert measurements[DerivedMetricName.IPC] == (10000 / 10)
    assert measurements[DerivedMetricName.IPS] == (10000 / 5)

    # Assuming cache misses increase is 10k over all 50k cache references
    # Cache hit ratio should be 40k / 50k = 80%
    assert measurements[DerivedMetricName.CACHE_HIT_RATIO] == 0.8

    # 10k misses per 10k instructions / 1000 = 10k / 10
    assert measurements[DerivedMetricName.CACHE_MISSES_PER_KILO_INSTRUCTIONS] == 1000
