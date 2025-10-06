import { useQuery } from '@tanstack/react-query';
import { useParams, Link } from 'react-router-dom';
import { servicesApi, journeysApi } from '../services/api';
import { ArrowLeft, PlayCircle } from 'lucide-react';
import ConfidenceBadge from '../components/ConfidenceBadge';

export default function ServiceDetail() {
  const { id } = useParams<{ id: string }>();

  const { data: service, isLoading: serviceLoading } = useQuery({
    queryKey: ['service', id],
    queryFn: async () => {
      const response = await servicesApi.getById(id!);
      return response.data;
    },
    enabled: !!id,
  });

  const { data: journeys, isLoading: journeysLoading } = useQuery({
    queryKey: ['journeys', id],
    queryFn: async () => {
      const response = await journeysApi.getByServiceId(id!);
      return response.data;
    },
    enabled: !!id,
  });

  if (serviceLoading || journeysLoading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div>
      <Link
        to="/"
        className="inline-flex items-center text-sm text-gray-500 hover:text-gray-700 mb-4"
      >
        <ArrowLeft className="h-4 w-4 mr-1" />
        Back to Services
      </Link>

      <div className="bg-white shadow rounded-lg p-6 mb-6">
        <div className="sm:flex sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{service?.name}</h1>
            <p className="mt-1 text-sm text-gray-500">
              {service?.owner_team} • {service?.environment}
            </p>
          </div>
          <div className="mt-4 sm:mt-0">
            <button
              type="button"
              className="inline-flex items-center px-4 py-2 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700"
            >
              <PlayCircle className="h-4 w-4 mr-2" />
              Trigger Analysis
            </button>
          </div>
        </div>
      </div>

      <div>
        <h2 className="text-lg font-medium text-gray-900 mb-4">User Journeys</h2>
        {journeys && journeys.length === 0 ? (
          <div className="bg-white shadow rounded-lg p-6 text-center text-gray-500">
            No user journeys discovered yet. Trigger analysis to discover journeys.
          </div>
        ) : (
          <div className="bg-white shadow rounded-lg overflow-hidden">
            <ul className="divide-y divide-gray-200">
              {journeys?.map((journey) => (
                <li key={journey.id}>
                  <Link
                    to={`/journeys/${journey.id}`}
                    className="block hover:bg-gray-50 transition-colors"
                  >
                    <div className="px-6 py-4">
                      <div className="flex items-center justify-between">
                        <div className="flex-1">
                          <h3 className="text-sm font-medium text-gray-900">
                            {journey.name}
                          </h3>
                          <p className="mt-1 text-sm text-gray-500">
                            {journey.entry_point} → {journey.exit_point}
                          </p>
                          <p className="mt-1 text-xs text-gray-400">
                            {journey.step_sequence.length} steps
                          </p>
                        </div>
                        <div>
                          <ConfidenceBadge score={journey.confidence_score} />
                        </div>
                      </div>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
