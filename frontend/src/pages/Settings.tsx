import { useState } from 'react';
import { Save, Database, Cloud, Brain, Bell } from 'lucide-react';

export default function Settings() {
  const [settings, setSettings] = useState({
    telemetry: {
      prometheusEndpoint: 'http://prometheus:9090',
      lokiEndpoint: 'http://loki:3100',
      otlpEndpoint: 'http://otlp-collector:4317',
    },
    llm: {
      provider: 'openai',
      endpoint: 'https://openrouter.ai/api/v1',
      model: 'anthropic/claude-3.5-sonnet',
    },
    storage: {
      s3Endpoint: 'http://minio:9000',
      bucket: 'slo-scout',
      milvusHost: 'milvus',
      milvusPort: '19530',
    },
    notifications: {
      enabled: true,
      webhookUrl: '',
      slackEnabled: false,
      emailEnabled: false,
    },
  });

  const handleSave = () => {
    // Mock save - would normally call API
    console.log('Saving settings:', settings);
  };

  return (
    <div>
      <div className="sm:flex sm:items-center sm:justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
          <p className="mt-2 text-sm text-gray-700">
            Configure SLO-Scout system settings
          </p>
        </div>
        <div className="mt-4 sm:mt-0">
          <button
            onClick={handleSave}
            className="inline-flex items-center px-4 py-2 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700"
          >
            <Save className="h-4 w-4 mr-2" />
            Save Changes
          </button>
        </div>
      </div>

      <div className="space-y-6">
        {/* Telemetry Sources */}
        <div className="bg-white shadow rounded-lg p-6">
          <div className="flex items-center mb-4">
            <Database className="h-5 w-5 text-blue-600 mr-2" />
            <h2 className="text-lg font-medium text-gray-900">Telemetry Sources</h2>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Prometheus Endpoint
              </label>
              <input
                type="text"
                value={settings.telemetry.prometheusEndpoint}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    telemetry: { ...settings.telemetry, prometheusEndpoint: e.target.value },
                  })
                }
                className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Loki Endpoint
              </label>
              <input
                type="text"
                value={settings.telemetry.lokiEndpoint}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    telemetry: { ...settings.telemetry, lokiEndpoint: e.target.value },
                  })
                }
                className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">
                OTLP Endpoint
              </label>
              <input
                type="text"
                value={settings.telemetry.otlpEndpoint}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    telemetry: { ...settings.telemetry, otlpEndpoint: e.target.value },
                  })
                }
                className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
              />
            </div>
          </div>
        </div>

        {/* LLM Configuration */}
        <div className="bg-white shadow rounded-lg p-6">
          <div className="flex items-center mb-4">
            <Brain className="h-5 w-5 text-purple-600 mr-2" />
            <h2 className="text-lg font-medium text-gray-900">LLM Configuration</h2>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-gray-700">Provider</label>
              <select
                value={settings.llm.provider}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    llm: { ...settings.llm, provider: e.target.value },
                  })
                }
                className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
              >
                <option value="openai">OpenAI Compatible</option>
                <option value="local">Local Model</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Endpoint</label>
              <input
                type="text"
                value={settings.llm.endpoint}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    llm: { ...settings.llm, endpoint: e.target.value },
                  })
                }
                className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
              />
            </div>
            <div className="sm:col-span-2">
              <label className="block text-sm font-medium text-gray-700">Model</label>
              <input
                type="text"
                value={settings.llm.model}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    llm: { ...settings.llm, model: e.target.value },
                  })
                }
                className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
              />
            </div>
          </div>
        </div>

        {/* Storage Configuration */}
        <div className="bg-white shadow rounded-lg p-6">
          <div className="flex items-center mb-4">
            <Cloud className="h-5 w-5 text-green-600 mr-2" />
            <h2 className="text-lg font-medium text-gray-900">Storage Configuration</h2>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-gray-700">
                S3 Endpoint
              </label>
              <input
                type="text"
                value={settings.storage.s3Endpoint}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    storage: { ...settings.storage, s3Endpoint: e.target.value },
                  })
                }
                className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Bucket</label>
              <input
                type="text"
                value={settings.storage.bucket}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    storage: { ...settings.storage, bucket: e.target.value },
                  })
                }
                className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Milvus Host
              </label>
              <input
                type="text"
                value={settings.storage.milvusHost}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    storage: { ...settings.storage, milvusHost: e.target.value },
                  })
                }
                className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Milvus Port
              </label>
              <input
                type="text"
                value={settings.storage.milvusPort}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    storage: { ...settings.storage, milvusPort: e.target.value },
                  })
                }
                className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
              />
            </div>
          </div>
        </div>

        {/* Notifications */}
        <div className="bg-white shadow rounded-lg p-6">
          <div className="flex items-center mb-4">
            <Bell className="h-5 w-5 text-yellow-600 mr-2" />
            <h2 className="text-lg font-medium text-gray-900">Notifications</h2>
          </div>
          <div className="space-y-4">
            <div className="flex items-center">
              <input
                type="checkbox"
                checked={settings.notifications.enabled}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    notifications: { ...settings.notifications, enabled: e.target.checked },
                  })
                }
                className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
              />
              <label className="ml-2 block text-sm text-gray-900">
                Enable notifications
              </label>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Webhook URL
              </label>
              <input
                type="text"
                value={settings.notifications.webhookUrl}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    notifications: { ...settings.notifications, webhookUrl: e.target.value },
                  })
                }
                className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                placeholder="https://hooks.example.com/webhook"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
