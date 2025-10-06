import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Layout from './components/Layout';
import Services from './pages/Services';
import ServiceDetail from './pages/ServiceDetail';
import JourneyDetail from './pages/JourneyDetail';
import Artifacts from './pages/Artifacts';
import Settings from './pages/Settings';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Services />} />
            <Route path="services/:id" element={<ServiceDetail />} />
            <Route path="journeys/:id" element={<JourneyDetail />} />
            <Route path="artifacts" element={<Artifacts />} />
            <Route path="settings" element={<Settings />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
