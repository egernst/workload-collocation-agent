
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


from common import command, json, pod, \
    wrapper_kafka_topic, wrapper_kafka_brokers, wrapper_log_level, \
    wrapper_labels, slo, cpu_list

command.append(
    "taskset -c {cpu_list} /tensorflow_benchmark_training_wrapper.pex --command '/usr/bin/python3.5"
    " -u /root/benchmarks/scripts/tf_cnn_benchmarks/tf_cnn_benchmarks.py "
    "--datasets_use_prefetch=True --batch_group_size=1 --device=cpu "
    "--data_format=NHWC --data_name=cifar10 --batch_size=64 --display_every=1 "
    "--model=resnet56 --train_dir=/saved_model/ --num_epochs=100 "
    "--num_intra_threads=10 --num_inter_threads=10' "
    "--metric_name_prefix 'tensorflow_benchmark_' "
    "--stderr 0 --kafka_brokers '{kafka_brokers}' --kafka_topic {kafka_topic} "
    "--log_level {log_level} "
    "--slo {slo} --sli_metric_name tensorflow_benchmark_training_speed "
    "--inverse_sli_metric_value "
    "--peak_load 1 --load_metric_name const "
    "--labels '{labels}'".format(
                cpu_list=cpu_list,
                kafka_brokers=wrapper_kafka_brokers,
                log_level=wrapper_log_level,
                kafka_topic=wrapper_kafka_topic,
                labels=json.dumps(wrapper_labels), slo=slo))


json_format = json.dumps(pod)
print(json_format)
