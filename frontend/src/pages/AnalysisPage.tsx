import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { servicesApi, analysisApi } from '../services/api';
import AnalysisJobList from '../components/AnalysisJobList';
import { PlayCircle, Loader2, AlertCircle, CheckCircle2 } from 'lucide-react';

export default function AnalysisPage() {
  const [selectedServiceId, setSelectedServiceId] = useState<string>('');
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const { data: services = [], isLoading: servicesLoading } = useQuery({
    queryKey: ['services'],
    queryFn: servicesApi.getAll,
  });

  const triggerMutation = useMutation({
    mutationFn: (serviceId: string) => analysisApi.trigger(serviceId),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['analysis-jobs'] });
      setSuccessMessage(`Analysis job started successfully! Job ID: ${data.job_id}`);
      setTimeout(() => setSuccessMessage(null), 5000);
    },
  });

  const handleTriggerAnalysis = () => {
    if (!selectedServiceId) return;
    triggerMutation.mutate(selectedServiceId);
  };

  const activeServices = services.filter(s => s.status === 'active');

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Analysis</h1>
        <p className="text-gray-600">
          Trigger SLO analysis jobs and monitor their progress
        </p>
      </div>

      {/* Trigger Section */}
      <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-6 mb-8">
        <h2 className="text-xl font-semibold text-gray-900 mb-4">Trigger New Analysis</h2>
        <p className="text-sm text-gray-600 mb-6">
          Start an analysis job to automatically discover user journeys, SLIs, and generate SLOs for a service.
        </p>

        {successMessage && (
          <div className="mb-6 bg-green-50 border border-green-200 rounded-md p-4" role="status">
            <div className="flex items-start gap-3">
              <CheckCircle2 className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" aria-hidden="true" />
              <div>
                <h3 className="text-sm font-medium text-green-800">Success</h3>
                <p className="text-sm text-green-700 mt-1">{successMessage}</p>
              </div>
            </div>
          </div>
        )}

        {triggerMutation.isError && (
          <div className="mb-6 bg-red-50 border border-red-200 rounded-md p-4" role="alert">
            <div className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" aria-hidden="true" />
              <div>
                <h3 className="text-sm font-medium text-red-800">Error</h3>
                <p className="text-sm text-red-700 mt-1">
                  {triggerMutation.error instanceof Error
                    ? triggerMutation.error.message
                    : 'Failed to trigger analysis job. Please try again.'}
                </p>
              </div>
            </div>
          </div>
        )}

        <div className="flex flex-col sm:flex-row gap-4">
          <div className="flex-1">
            <label htmlFor="service-select" className="block text-sm font-medium text-gray-700 mb-2">
              Select Service <span className="text-red-500" aria-label="required">*</span>
            </label>
            {servicesLoading ? (
              <div className="flex items-center gap-2 px-3 py-2 border border-gray-300 rounded-md bg-gray-50">
                <Loader2 className="w-4 h-4 animate-spin text-gray-600" aria-hidden="true" />
                <span className="text-sm text-gray-600">Loading services...</span>
              </div>
            ) : activeServices.length === 0 ? (
              <div className="px-3 py-2 border border-gray-300 rounded-md bg-gray-50 text-sm text-gray-600">
                No active services available
              </div>
            ) : (
              <select
                id="service-select"
                value={selectedServiceId}
                onChange={(e) => setSelectedServiceId(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                disabled={triggerMutation.isPending}
              >
                <option value="">-- Select a service --</option>
                {activeServices.map((service) => (
                  <option key={service.id} value={service.id}>
                    {service.name} ({service.environment})
                  </option>
                ))}
              </select>
            )}
          </div>

          <div className="flex items-end">
            <button
              onClick={handleTriggerAnalysis}
              disabled={!selectedServiceId || triggerMutation.isPending || servicesLoading}
              className="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2 h-[42px]"
            >
              {triggerMutation.isPending ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" aria-hidden="true" />
                  Starting...
                </>
              ) : (
                <>
                  <PlayCircle className="w-5 h-5" aria-hidden="true" />
                  Start Analysis
                </>
              )}
            </button>
          </div>
        </div>

        <div className="mt-4 p-4 bg-blue-50 border border-blue-200 rounded-md">
          <h3 className="text-sm font-medium text-blue-900 mb-2">What happens during analysis?</h3>
          <ul className="text-sm text-blue-800 space-y-1 list-disc list-inside">
            <li>Telemetry data is collected from configured endpoints</li>
            <li>User journeys are discovered from traces</li>
            <li>SLIs are automatically generated from metrics</li>
            <li>SLO proposals are created based on historical data</li>
            <li>Artifacts (dashboards, alerts, runbooks) are generated</li>
          </ul>
        </div>
      </div>

      {/* Jobs List */}
      <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-6">
        <AnalysisJobList
          serviceId={selectedServiceId || undefined}
          autoRefresh={true}
          refreshInterval={5000}
        />
      </div>
    </div>
  );
}
