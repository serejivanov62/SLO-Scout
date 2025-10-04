"""
Trace graph builder per T087
Analyzes traces, builds service dependency graph
Identifies user journeys from RUM entry points to terminal spans
"""
from typing import List, Dict, Set, Tuple, Optional
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class SpanNode:
    """Represents a span in the trace graph"""
    span_id: str
    span_name: str
    service_name: str
    duration_ms: float
    parent_span_id: Optional[str]
    trace_id: str
    attributes: Dict[str, str]


@dataclass
class UserJourney:
    """Represents a discovered user journey"""
    name: str
    entry_point: str
    exit_point: str
    step_sequence: List[Dict]
    sample_trace_ids: List[str]
    traffic_volume: int
    avg_duration_ms: float
    error_rate: float


class TraceGraphBuilder:
    """
    Builds service dependency graph from traces

    Per data-model.md UserJourney:
    - Identifies critical paths from RUM entry points
    - Builds step sequences with duration/error stats
    """

    def __init__(self):
        self.traces: Dict[str, List[SpanNode]] = defaultdict(list)
        self.journeys: Dict[str, UserJourney] = {}

    def add_trace(self, trace_id: str, spans: List[SpanNode]) -> None:
        """Add trace to the graph"""
        self.traces[trace_id] = spans

    def build_graph(self) -> Dict[str, Set[str]]:
        """
        Build service dependency graph

        Returns:
            Dict mapping service to set of dependent services
        """
        graph = defaultdict(set)

        for trace_id, spans in self.traces.items():
            # Build parent-child relationships
            span_map = {span.span_id: span for span in spans}

            for span in spans:
                if span.parent_span_id and span.parent_span_id in span_map:
                    parent = span_map[span.parent_span_id]
                    if parent.service_name != span.service_name:
                        # Cross-service call
                        graph[parent.service_name].add(span.service_name)

        return graph

    def identify_journeys(
        self,
        min_traffic_volume: int = 100,
        min_trace_count: int = 10
    ) -> List[UserJourney]:
        """
        Identify user journeys from trace analysis

        Args:
            min_traffic_volume: Minimum traffic to qualify as journey
            min_trace_count: Minimum number of traces required

        Returns:
            List of discovered user journeys
        """
        # Group traces by entry point (first span)
        entry_points = defaultdict(list)

        for trace_id, spans in self.traces.items():
            if not spans:
                continue

            # Sort by timestamp to find root span
            root_span = min(spans, key=lambda s: s.span_id)

            # Entry point is the root span name
            entry_point = f"{root_span.service_name}:{root_span.span_name}"
            entry_points[entry_point].append((trace_id, spans))

        # Analyze each entry point
        journeys = []

        for entry_point, trace_list in entry_points.items():
            if len(trace_list) < min_trace_count:
                continue

            # Build step sequence from common patterns
            step_sequence = self._extract_step_sequence(trace_list)

            # Find exit point (terminal span)
            exit_points = defaultdict(int)
            for trace_id, spans in trace_list:
                # Terminal span = leaf node with no children
                terminal_spans = [
                    s for s in spans
                    if not any(s2.parent_span_id == s.span_id for s2 in spans)
                ]
                for ts in terminal_spans:
                    exit_points[f"{ts.service_name}:{ts.span_name}"] += 1

            # Most common exit point
            exit_point = max(exit_points.items(), key=lambda x: x[1])[0]

            # Calculate metrics
            durations = []
            errors = 0
            for trace_id, spans in trace_list:
                total_duration = sum(s.duration_ms for s in spans)
                durations.append(total_duration)
                if any(s.attributes.get('error') == 'true' for s in spans):
                    errors += 1

            avg_duration = sum(durations) / len(durations) if durations else 0
            error_rate = errors / len(trace_list) if trace_list else 0

            # Create journey
            journey = UserJourney(
                name=self._generate_journey_name(entry_point, exit_point),
                entry_point=entry_point,
                exit_point=exit_point,
                step_sequence=step_sequence,
                sample_trace_ids=[t[0] for t in trace_list[:10]],  # Sample 10 traces
                traffic_volume=len(trace_list),
                avg_duration_ms=avg_duration,
                error_rate=error_rate
            )

            journeys.append(journey)

        return journeys

    def _extract_step_sequence(
        self,
        trace_list: List[Tuple[str, List[SpanNode]]]
    ) -> List[Dict]:
        """
        Extract common step sequence from traces

        Returns:
            [
                {"span_name": "...", "service_name": "...", "duration_p50": 123, "error_rate": 0.01},
                ...
            ]
        """
        # Collect all span sequences
        sequences = []
        for trace_id, spans in trace_list:
            # Sort spans by parent-child relationships
            sequence = self._topological_sort(spans)
            sequences.append(sequence)

        # Find common steps
        step_stats = defaultdict(lambda: {"durations": [], "errors": 0})

        for sequence in sequences:
            for span in sequence:
                key = f"{span.service_name}:{span.span_name}"
                step_stats[key]["durations"].append(span.duration_ms)
                if span.attributes.get('error') == 'true':
                    step_stats[key]["errors"] += 1

        # Build step sequence
        steps = []
        for step_key, stats in step_stats.items():
            service_name, span_name = step_key.split(':', 1)
            durations = sorted(stats["durations"])
            p50_duration = durations[len(durations) // 2] if durations else 0

            steps.append({
                "span_name": span_name,
                "service_name": service_name,
                "duration_p50": p50_duration,
                "error_rate": stats["errors"] / len(durations) if durations else 0
            })

        return steps

    def _topological_sort(self, spans: List[SpanNode]) -> List[SpanNode]:
        """Sort spans by parent-child relationships"""
        span_map = {span.span_id: span for span in spans}
        children = defaultdict(list)

        for span in spans:
            if span.parent_span_id:
                children[span.parent_span_id].append(span.span_id)

        # Find root (no parent)
        root = next((s for s in spans if not s.parent_span_id), None)
        if not root:
            return spans

        # BFS traversal
        result = []
        queue = [root.span_id]
        visited = set()

        while queue:
            span_id = queue.pop(0)
            if span_id in visited:
                continue

            visited.add(span_id)
            if span_id in span_map:
                result.append(span_map[span_id])
                queue.extend(children[span_id])

        return result

    def _generate_journey_name(self, entry: str, exit: str) -> str:
        """Generate human-readable journey name"""
        # Extract span names
        entry_span = entry.split(':')[-1]
        exit_span = exit.split(':')[-1]

        # Simplify names
        name = f"{entry_span}-to-{exit_span}"
        return name.replace('/', '-').replace('_', '-').lower()
