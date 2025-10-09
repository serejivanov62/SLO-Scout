import { useState } from 'react';
import { servicesApi } from '../services/api';
import { AlertCircle, Plus, Trash2, Loader2 } from 'lucide-react';

interface TelemetryEndpoint {
  key: string;
  value: string;
}

interface ServiceFormProps {
  onSuccess?: () => void;
}

export default function ServiceForm({ onSuccess }: ServiceFormProps) {
  const [formData, setFormData] = useState({
    name: '',
    environment: 'development' as 'development' | 'staging' | 'production',
    owner_team: '',
  });

  const [endpoints, setEndpoints] = useState<TelemetryEndpoint[]>([
    { key: 'prometheus', value: '' },
    { key: 'jaeger', value: '' },
  ]);

  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState(false);

  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!formData.name.trim()) {
      newErrors.name = 'Service name is required';
    } else if (formData.name.length < 3) {
      newErrors.name = 'Service name must be at least 3 characters';
    }

    if (!formData.owner_team.trim()) {
      newErrors.owner_team = 'Owner team is required';
    }

    const validEndpoints = endpoints.filter(e => e.key.trim() && e.value.trim());
    if (validEndpoints.length === 0) {
      newErrors.endpoints = 'At least one telemetry endpoint is required';
    }

    endpoints.forEach((endpoint, index) => {
      if (endpoint.key.trim() && endpoint.value.trim()) {
        try {
          new URL(endpoint.value);
        } catch {
          newErrors[`endpoint_${index}`] = 'Must be a valid URL';
        }
      }
    });

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleAddEndpoint = () => {
    setEndpoints([...endpoints, { key: '', value: '' }]);
  };

  const handleRemoveEndpoint = (index: number) => {
    if (endpoints.length > 1) {
      setEndpoints(endpoints.filter((_, i) => i !== index));
    }
  };

  const handleEndpointChange = (index: number, field: 'key' | 'value', value: string) => {
    const newEndpoints = [...endpoints];
    newEndpoints[index][field] = value;
    setEndpoints(newEndpoints);

    // Clear error for this field
    if (errors[`endpoint_${index}`]) {
      const newErrors = { ...errors };
      delete newErrors[`endpoint_${index}`];
      setErrors(newErrors);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError(null);
    setSubmitSuccess(false);

    if (!validateForm()) {
      return;
    }

    setIsSubmitting(true);

    try {
      const telemetry_endpoints: Record<string, string> = {};
      endpoints.forEach(endpoint => {
        if (endpoint.key.trim() && endpoint.value.trim()) {
          telemetry_endpoints[endpoint.key.trim()] = endpoint.value.trim();
        }
      });

      await servicesApi.create({
        name: formData.name.trim(),
        environment: formData.environment,
        owner_team: formData.owner_team.trim(),
        telemetry_endpoints,
      });

      setSubmitSuccess(true);

      // Reset form
      setFormData({
        name: '',
        environment: 'development',
        owner_team: '',
      });
      setEndpoints([
        { key: 'prometheus', value: '' },
        { key: 'jaeger', value: '' },
      ]);
      setErrors({});

      if (onSuccess) {
        onSuccess();
      }
    } catch (error: any) {
      setSubmitError(
        error.response?.data?.detail ||
        error.message ||
        'Failed to create service. Please try again.'
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6 bg-white p-6 rounded-lg shadow-sm border border-gray-200">
      <div>
        <h2 className="text-xl font-semibold text-gray-900 mb-4">Register New Service</h2>
        <p className="text-sm text-gray-600 mb-6">
          Add a new service to enable SLO analysis and monitoring.
        </p>
      </div>

      {submitError && (
        <div className="bg-red-50 border border-red-200 rounded-md p-4 flex items-start gap-3" role="alert">
          <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" aria-hidden="true" />
          <div>
            <h3 className="text-sm font-medium text-red-800">Error</h3>
            <p className="text-sm text-red-700 mt-1">{submitError}</p>
          </div>
        </div>
      )}

      {submitSuccess && (
        <div className="bg-green-50 border border-green-200 rounded-md p-4" role="status">
          <p className="text-sm text-green-800">Service created successfully!</p>
        </div>
      )}

      <div className="space-y-4">
        <div>
          <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-1">
            Service Name <span className="text-red-500" aria-label="required">*</span>
          </label>
          <input
            type="text"
            id="name"
            value={formData.name}
            onChange={(e) => {
              setFormData({ ...formData, name: e.target.value });
              if (errors.name) {
                const newErrors = { ...errors };
                delete newErrors.name;
                setErrors(newErrors);
              }
            }}
            className={`w-full px-3 py-2 border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
              errors.name ? 'border-red-300' : 'border-gray-300'
            }`}
            placeholder="e.g., payment-service"
            aria-invalid={!!errors.name}
            aria-describedby={errors.name ? 'name-error' : undefined}
          />
          {errors.name && (
            <p id="name-error" className="mt-1 text-sm text-red-600">{errors.name}</p>
          )}
        </div>

        <div>
          <label htmlFor="environment" className="block text-sm font-medium text-gray-700 mb-1">
            Environment <span className="text-red-500" aria-label="required">*</span>
          </label>
          <select
            id="environment"
            value={formData.environment}
            onChange={(e) => setFormData({ ...formData, environment: e.target.value as any })}
            className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="development">Development</option>
            <option value="staging">Staging</option>
            <option value="production">Production</option>
          </select>
        </div>

        <div>
          <label htmlFor="owner_team" className="block text-sm font-medium text-gray-700 mb-1">
            Owner Team <span className="text-red-500" aria-label="required">*</span>
          </label>
          <input
            type="text"
            id="owner_team"
            value={formData.owner_team}
            onChange={(e) => {
              setFormData({ ...formData, owner_team: e.target.value });
              if (errors.owner_team) {
                const newErrors = { ...errors };
                delete newErrors.owner_team;
                setErrors(newErrors);
              }
            }}
            className={`w-full px-3 py-2 border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
              errors.owner_team ? 'border-red-300' : 'border-gray-300'
            }`}
            placeholder="e.g., platform-team"
            aria-invalid={!!errors.owner_team}
            aria-describedby={errors.owner_team ? 'owner-error' : undefined}
          />
          {errors.owner_team && (
            <p id="owner-error" className="mt-1 text-sm text-red-600">{errors.owner_team}</p>
          )}
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="block text-sm font-medium text-gray-700">
              Telemetry Endpoints <span className="text-red-500" aria-label="required">*</span>
            </label>
            <button
              type="button"
              onClick={handleAddEndpoint}
              className="text-sm text-blue-600 hover:text-blue-700 flex items-center gap-1"
              aria-label="Add telemetry endpoint"
            >
              <Plus className="w-4 h-4" aria-hidden="true" />
              Add Endpoint
            </button>
          </div>

          <div className="space-y-3">
            {endpoints.map((endpoint, index) => (
              <div key={index} className="flex gap-2">
                <input
                  type="text"
                  value={endpoint.key}
                  onChange={(e) => handleEndpointChange(index, 'key', e.target.value)}
                  className="w-1/3 px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Type (e.g., prometheus)"
                  aria-label={`Endpoint type ${index + 1}`}
                />
                <input
                  type="url"
                  value={endpoint.value}
                  onChange={(e) => handleEndpointChange(index, 'value', e.target.value)}
                  className={`flex-1 px-3 py-2 border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                    errors[`endpoint_${index}`] ? 'border-red-300' : 'border-gray-300'
                  }`}
                  placeholder="https://prometheus.example.com"
                  aria-label={`Endpoint URL ${index + 1}`}
                  aria-invalid={!!errors[`endpoint_${index}`]}
                  aria-describedby={errors[`endpoint_${index}`] ? `endpoint-error-${index}` : undefined}
                />
                <button
                  type="button"
                  onClick={() => handleRemoveEndpoint(index)}
                  disabled={endpoints.length === 1}
                  className="p-2 text-red-600 hover:text-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
                  aria-label={`Remove endpoint ${index + 1}`}
                >
                  <Trash2 className="w-5 h-5" aria-hidden="true" />
                </button>
              </div>
            ))}
            {errors.endpoints && (
              <p className="text-sm text-red-600">{errors.endpoints}</p>
            )}
          </div>
        </div>
      </div>

      <div className="flex justify-end pt-4 border-t border-gray-200">
        <button
          type="submit"
          disabled={isSubmitting}
          className="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
        >
          {isSubmitting ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
              Creating...
            </>
          ) : (
            'Create Service'
          )}
        </button>
      </div>
    </form>
  );
}
