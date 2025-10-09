import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { servicesApi } from '../services/api';
import ServiceForm from '../components/ServiceForm';
import { Server, Plus, ExternalLink, Loader2, AlertCircle } from 'lucide-react';

export default function ServicesPage() {
  const [showForm, setShowForm] = useState(false);

  const { data: services = [], isLoading, error, refetch } = useQuery({
    queryKey: ['services'],
    queryFn: servicesApi.getAll,
  });

  const handleServiceCreated = () => {
    refetch();
    setShowForm(false);
  };

  const getEnvironmentColor = (env: string) => {
    switch (env) {
      case 'production':
        return 'bg-red-100 text-red-800 border-red-200';
      case 'staging':
        return 'bg-yellow-100 text-yellow-800 border-yellow-200';
      case 'development':
        return 'bg-blue-100 text-blue-800 border-blue-200';
      default:
        return 'bg-gray-100 text-gray-800 border-gray-200';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active':
        return 'bg-green-100 text-green-800 border-green-200';
      case 'inactive':
        return 'bg-gray-100 text-gray-800 border-gray-200';
      case 'archived':
        return 'bg-orange-100 text-orange-800 border-orange-200';
      default:
        return 'bg-gray-100 text-gray-800 border-gray-200';
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 mb-2">Services</h1>
            <p className="text-gray-600">
              Manage and monitor your services for SLO analysis
            </p>
          </div>
          <button
            onClick={() => setShowForm(!showForm)}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors flex items-center gap-2"
          >
            <Plus className="w-5 h-5" aria-hidden="true" />
            {showForm ? 'Hide Form' : 'Add Service'}
          </button>
        </div>
      </div>

      {/* Service Form */}
      {showForm && (
        <div className="mb-8">
          <ServiceForm onSuccess={handleServiceCreated} />
        </div>
      )}

      {/* Services List */}
      <div>
        <h2 className="text-xl font-semibold text-gray-900 mb-4">
          Registered Services ({services.length})
        </h2>

        {isLoading ? (
          <div className="flex items-center justify-center py-12" role="status">
            <Loader2 className="w-8 h-8 text-blue-600 animate-spin" aria-hidden="true" />
            <span className="sr-only">Loading services...</span>
          </div>
        ) : error ? (
          <div className="bg-red-50 border border-red-200 rounded-md p-6" role="alert">
            <div className="flex items-start gap-3">
              <AlertCircle className="w-6 h-6 text-red-600 flex-shrink-0 mt-0.5" aria-hidden="true" />
              <div>
                <h3 className="text-lg font-medium text-red-800">Error loading services</h3>
                <p className="text-sm text-red-700 mt-1">
                  {error instanceof Error ? error.message : 'Failed to load services'}
                </p>
                <button
                  onClick={() => refetch()}
                  className="mt-3 text-sm text-red-800 underline hover:no-underline"
                >
                  Try again
                </button>
              </div>
            </div>
          </div>
        ) : services.length === 0 ? (
          <div className="text-center py-12 bg-gray-50 rounded-lg border-2 border-dashed border-gray-300">
            <Server className="w-16 h-16 text-gray-400 mx-auto mb-4" aria-hidden="true" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">No services yet</h3>
            <p className="text-gray-600 mb-4">
              Get started by adding your first service
            </p>
            <button
              onClick={() => setShowForm(true)}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors inline-flex items-center gap-2"
            >
              <Plus className="w-5 h-5" aria-hidden="true" />
              Add Your First Service
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6" role="list">
            {services.map((service) => (
              <div
                key={service.id}
                className="bg-white border border-gray-200 rounded-lg shadow-sm hover:shadow-md transition-shadow overflow-hidden"
                role="listitem"
              >
                <div className="p-6">
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <Server className="w-5 h-5 text-gray-600" aria-hidden="true" />
                      <h3 className="text-lg font-semibold text-gray-900">
                        {service.name}
                      </h3>
                    </div>
                    <Link
                      to={`/services/${service.id}`}
                      className="text-blue-600 hover:text-blue-700"
                      aria-label={`View ${service.name} details`}
                    >
                      <ExternalLink className="w-5 h-5" aria-hidden="true" />
                    </Link>
                  </div>

                  <div className="space-y-3">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span
                        className={`px-2.5 py-0.5 text-xs font-medium rounded-md border ${getEnvironmentColor(service.environment)}`}
                      >
                        {service.environment}
                      </span>
                      <span
                        className={`px-2.5 py-0.5 text-xs font-medium rounded-md border ${getStatusColor(service.status)}`}
                      >
                        {service.status}
                      </span>
                    </div>

                    <div>
                      <div className="text-sm text-gray-600">
                        <span className="font-medium">Owner:</span> {service.owner_team}
                      </div>
                    </div>

                    <div>
                      <div className="text-sm font-medium text-gray-700 mb-1">
                        Telemetry Endpoints:
                      </div>
                      <div className="space-y-1">
                        {Object.entries(service.telemetry_endpoints).map(([key, value]) => (
                          <div
                            key={key}
                            className="flex items-center gap-2 text-xs bg-gray-50 px-2 py-1 rounded"
                          >
                            <span className="font-medium text-gray-700 capitalize">
                              {key}:
                            </span>
                            <span className="text-gray-600 truncate flex-1" title={value}>
                              {value}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="pt-3 border-t border-gray-200 text-xs text-gray-500">
                      <div>Created: {new Date(service.created_at).toLocaleDateString()}</div>
                      {service.updated_at !== service.created_at && (
                        <div>Updated: {new Date(service.updated_at).toLocaleDateString()}</div>
                      )}
                    </div>
                  </div>
                </div>

                <div className="px-6 py-3 bg-gray-50 border-t border-gray-200">
                  <Link
                    to={`/services/${service.id}`}
                    className="text-sm text-blue-600 hover:text-blue-700 font-medium"
                  >
                    View Details →
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
