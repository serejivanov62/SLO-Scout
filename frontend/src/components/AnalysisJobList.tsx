import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { analysisApi } from '../services/api';
import { AnalysisJob } from '../types';
import { CheckCircle2, XCircle, Clock, Loader2, PlayCircle } from 'lucide-react';

interface AnalysisJobListProps {
  serviceId?: string;
  autoRefresh?: boolean;
  refreshInterval?: number;
}

export default function AnalysisJobList({
  serviceId,
  autoRefresh = true,
  refreshInterval = 5000,
}: AnalysisJobListProps) {
  const [expandedJobs, setExpandedJobs] = useState<Set<string>>(new Set());

  const { data: jobs = [], isLoading, error, refetch } = useQuery({
    queryKey: ['analysis-jobs', serviceId],
    queryFn: async () => {
      const allJobs = await analysisApi.getAll();
      return serviceId
        ? allJobs.filter(job => job.service_id === serviceId)
        : allJobs;
    },
    refetchInterval: autoRefresh ? refreshInterval : false,
  });

  useEffect(() => {
    // Auto-expand jobs that are in progress
    const inProgressJobs = jobs
      .filter(job => job.status === 'processing' || job.status === 'queued')
      .map(job => job.job_id);

    if (inProgressJobs.length > 0) {
      setExpandedJobs(prev => {
        const newSet = new Set(prev);
        inProgressJobs.forEach(id => newSet.add(id));
        return newSet;
      });
    }
  }, [jobs]);

  const toggleExpanded = (jobId: string) => {
    setExpandedJobs(prev => {
      const newSet = new Set(prev);
      if (newSet.has(jobId)) {
        newSet.delete(jobId);
      } else {
        newSet.add(jobId);
      }
      return newSet;
    });
  };

  const getStatusIcon = (status: AnalysisJob['status']) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="w-5 h-5 text-green-600" aria-hidden="true" />;
      case 'failed':
        return <XCircle className="w-5 h-5 text-red-600" aria-hidden="true" />;
      case 'processing':
        return <Loader2 className="w-5 h-5 text-blue-600 animate-spin" aria-hidden="true" />;
      case 'queued':
        return <Clock className="w-5 h-5 text-yellow-600" aria-hidden="true" />;
      default:
        return <PlayCircle className="w-5 h-5 text-gray-600" aria-hidden="true" />;
    }
  };

  const getStatusColor = (status: AnalysisJob['status']) => {
    switch (status) {
      case 'completed':
        return 'bg-green-100 text-green-800 border-green-200';
      case 'failed':
        return 'bg-red-100 text-red-800 border-red-200';
      case 'processing':
        return 'bg-blue-100 text-blue-800 border-blue-200';
      case 'queued':
        return 'bg-yellow-100 text-yellow-800 border-yellow-200';
      default:
        return 'bg-gray-100 text-gray-800 border-gray-200';
    }
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return new Intl.DateTimeFormat('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(date);
  };

  const calculateDuration = (job: AnalysisJob) => {
    const start = new Date(job.created_at);
    const end = job.completed_at ? new Date(job.completed_at) : new Date();
    const durationMs = end.getTime() - start.getTime();
    const seconds = Math.floor(durationMs / 1000);
    const minutes = Math.floor(seconds / 60);

    if (minutes > 0) {
      return `${minutes}m ${seconds % 60}s`;
    }
    return `${seconds}s`;
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12" role="status">
        <Loader2 className="w-8 h-8 text-blue-600 animate-spin" aria-hidden="true" />
        <span className="sr-only">Loading analysis jobs...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-md p-4" role="alert">
        <div className="flex items-start gap-3">
          <XCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" aria-hidden="true" />
          <div>
            <h3 className="text-sm font-medium text-red-800">Error loading jobs</h3>
            <p className="text-sm text-red-700 mt-1">
              {error instanceof Error ? error.message : 'Failed to load analysis jobs'}
            </p>
            <button
              onClick={() => refetch()}
              className="mt-2 text-sm text-red-800 underline hover:no-underline"
            >
              Try again
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (jobs.length === 0) {
    return (
      <div className="text-center py-12 bg-gray-50 rounded-lg border border-gray-200">
        <PlayCircle className="w-12 h-12 text-gray-400 mx-auto mb-3" aria-hidden="true" />
        <h3 className="text-lg font-medium text-gray-900 mb-1">No analysis jobs</h3>
        <p className="text-sm text-gray-600">
          {serviceId
            ? 'Start an analysis job for this service to see results here.'
            : 'No analysis jobs have been run yet.'}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900">
          Analysis Jobs ({jobs.length})
        </h3>
        {autoRefresh && (
          <div className="flex items-center gap-2 text-sm text-gray-600">
            <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
            <span>Auto-refreshing every {refreshInterval / 1000}s</span>
          </div>
        )}
      </div>

      <div className="space-y-3" role="list">
        {jobs.map((job) => {
          const isExpanded = expandedJobs.has(job.job_id);
          const isActive = job.status === 'processing' || job.status === 'queued';

          return (
            <div
              key={job.job_id}
              className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden"
              role="listitem"
            >
              <button
                onClick={() => toggleExpanded(job.job_id)}
                className="w-full px-4 py-4 flex items-start gap-4 hover:bg-gray-50 transition-colors text-left"
                aria-expanded={isExpanded}
                aria-controls={`job-details-${job.job_id}`}
              >
                <div className="flex-shrink-0 mt-0.5">
                  {getStatusIcon(job.status)}
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-mono text-sm text-gray-900 truncate">
                      {job.job_id}
                    </span>
                    <span
                      className={`px-2 py-0.5 text-xs font-medium rounded border ${getStatusColor(job.status)}`}
                    >
                      {job.status}
                    </span>
                  </div>

                  <div className="text-sm text-gray-600 space-y-1">
                    <div>Service: <span className="font-medium">{job.service_id}</span></div>
                    <div className="flex items-center gap-4 flex-wrap">
                      <span>Started: {formatDate(job.created_at)}</span>
                      {job.completed_at && (
                        <span>Completed: {formatDate(job.completed_at)}</span>
                      )}
                      <span>Duration: {calculateDuration(job)}</span>
                    </div>
                  </div>

                  {isActive && (
                    <div className="mt-3">
                      <div className="flex items-center justify-between text-sm mb-1">
                        <span className="text-gray-700 font-medium">Progress</span>
                        <span className="text-gray-600">{job.progress_percentage}%</span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
                        <div
                          className="bg-blue-600 h-full transition-all duration-500 ease-out"
                          style={{ width: `${job.progress_percentage}%` }}
                          role="progressbar"
                          aria-valuenow={job.progress_percentage}
                          aria-valuemin={0}
                          aria-valuemax={100}
                          aria-label="Job progress"
                        />
                      </div>
                    </div>
                  )}
                </div>

                <div className="flex-shrink-0 text-gray-400">
                  <svg
                    className={`w-5 h-5 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    aria-hidden="true"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
              </button>

              {isExpanded && (
                <div
                  id={`job-details-${job.job_id}`}
                  className="px-4 py-4 border-t border-gray-200 bg-gray-50"
                >
                  <dl className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                    <div>
                      <dt className="font-medium text-gray-700">Job ID</dt>
                      <dd className="font-mono text-gray-900 mt-1">{job.job_id}</dd>
                    </div>
                    <div>
                      <dt className="font-medium text-gray-700">Service ID</dt>
                      <dd className="font-mono text-gray-900 mt-1">{job.service_id}</dd>
                    </div>
                    <div>
                      <dt className="font-medium text-gray-700">Status</dt>
                      <dd className="text-gray-900 mt-1 capitalize">{job.status}</dd>
                    </div>
                    <div>
                      <dt className="font-medium text-gray-700">Progress</dt>
                      <dd className="text-gray-900 mt-1">{job.progress_percentage}%</dd>
                    </div>
                    <div>
                      <dt className="font-medium text-gray-700">Created At</dt>
                      <dd className="text-gray-900 mt-1">{new Date(job.created_at).toLocaleString()}</dd>
                    </div>
                    {job.completed_at && (
                      <div>
                        <dt className="font-medium text-gray-700">Completed At</dt>
                        <dd className="text-gray-900 mt-1">{new Date(job.completed_at).toLocaleString()}</dd>
                      </div>
                    )}
                    {job.error_message && (
                      <div className="sm:col-span-2">
                        <dt className="font-medium text-red-700">Error Message</dt>
                        <dd className="text-red-900 mt-1 font-mono text-xs bg-red-50 p-2 rounded border border-red-200">
                          {job.error_message}
                        </dd>
                      </div>
                    )}
                  </dl>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
