import { useQuery } from '@tanstack/react-query';
import { useParams, Link } from 'react-router-dom';
import { journeysApi, slisApi } from '../services/api';
import { ArrowLeft, ThumbsUp, Code } from 'lucide-react';
import ConfidenceBadge from '../components/ConfidenceBadge';

export default function JourneyDetail() {
  const { id } = useParams<{ id: string }>();

  const { data: journey, isLoading: journeyLoading } = useQuery({
    queryKey: ['journey', id],
    queryFn: async () => {
      const response = await journeysApi.getById(id!);
      return response.data;
    },
    enabled: !!id,
  });

  const { data: slis, isLoading: slisLoading } = useQuery({
    queryKey: ['slis', id],
    queryFn: async () => {
      const response = await slisApi.getByJourneyId(id!);
      return response.data;
    },
    enabled: !!id,
  });

  if (journeyLoading || slisLoading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div>
      <Link
        to={`/services/${journey?.service_id}`}
        className="inline-flex items-center text-sm text-gray-500 hover:text-gray-700 mb-4"
      >
        <ArrowLeft className="h-4 w-4 mr-1" />
        Back to Service
      </Link>

      <div className="bg-white shadow rounded-lg p-6 mb-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{journey?.name}</h1>
            <p className="mt-1 text-sm text-gray-500">
              {journey?.entry_point} → {journey?.exit_point}
            </p>
          </div>
          <ConfidenceBadge score={journey?.confidence_score || 0} size="lg" />
        </div>

        <div className="mt-6">
          <h3 className="text-sm font-medium text-gray-700 mb-2">Journey Steps</h3>
          <div className="flex flex-wrap gap-2">
            {journey?.step_sequence.map((step, index) => (
              <div
                key={index}
                className="inline-flex items-center bg-blue-50 text-blue-700 px-3 py-1 rounded-full text-sm"
              >
                <span className="font-medium mr-1">{step.order}.</span>
                {step.span_name}
                <span className="ml-1 text-blue-500">({step.service})</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div>
        <h2 className="text-lg font-medium text-gray-900 mb-4">Recommended SLIs</h2>
        {!slis || slis.length === 0 ? (
          <div className="bg-white shadow rounded-lg p-6 text-center text-gray-500">
            No SLI recommendations yet
          </div>
        ) : (
          <div className="space-y-4">
            {slis.map((sli) => (
              <div key={sli.id} className="bg-white shadow rounded-lg p-6">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center">
                      <h3 className="text-lg font-medium text-gray-900">{sli.name}</h3>
                      <span
                        className={`ml-3 inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                          sli.metric_type === 'latency'
                            ? 'bg-blue-100 text-blue-800'
                            : sli.metric_type === 'error_rate'
                            ? 'bg-red-100 text-red-800'
                            : sli.metric_type === 'availability'
                            ? 'bg-green-100 text-green-800'
                            : 'bg-gray-100 text-gray-800'
                        }`}
                      >
                        {sli.metric_type}
                      </span>
                      <div className="ml-3">
                        <ConfidenceBadge score={sli.confidence_score} />
                      </div>
                    </div>

                    <div className="mt-4">
                      <div className="flex items-start">
                        <Code className="h-5 w-5 text-gray-400 mr-2 mt-0.5" />
                        <pre className="flex-1 bg-gray-50 rounded p-3 text-sm text-gray-800 overflow-x-auto">
                          <code>{sli.metric_definition}</code>
                        </pre>
                      </div>
                    </div>

                    {sli.current_value !== null && (
                      <div className="mt-3 text-sm text-gray-600">
                        Current value:{' '}
                        <span className="font-medium text-gray-900">
                          {sli.current_value} {sli.unit}
                        </span>
                      </div>
                    )}

                    {sli.evidence_pointers && sli.evidence_pointers.length > 0 && (
                      <div className="mt-3">
                        <p className="text-xs text-gray-500">
                          Evidence: {sli.evidence_pointers.length} data point(s)
                        </p>
                      </div>
                    )}
                  </div>

                  <div className="ml-4 flex-shrink-0">
                    {!sli.approved_by ? (
                      <button className="inline-flex items-center px-4 py-2 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-green-600 hover:bg-green-700">
                        <ThumbsUp className="h-4 w-4 mr-2" />
                        Approve
                      </button>
                    ) : (
                      <span className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-green-100 text-green-800">
                        Approved
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
