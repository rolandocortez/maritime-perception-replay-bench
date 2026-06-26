from maritime_msgs.msg import RuntimeMetric, RuntimeMetricArray


def append_metric(
    array: RuntimeMetricArray,
    *,
    name: str,
    value: float,
    unit: str,
    window: str,
):
    metric = RuntimeMetric()
    metric.header = array.header
    metric.name = str(name)
    metric.value = float(value)
    metric.unit = str(unit)
    metric.window = str(window)
    array.metrics.append(metric)
