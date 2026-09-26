import { useEffect, useRef, useState } from 'react';
import type { Overview } from './App';

type OverviewResponse =
  | { status: 'not_generated'; overview: null }
  | { status: 'ready'; overview: Overview };
type ViewState =
  | { status: 'loading' | 'empty' | 'generating' }
  | { status: 'ready'; overview: Overview }
  | { status: 'error'; message: string; retry: 'load' | 'generate' };

function isOverview(value: unknown): value is Overview {
  if (!value || typeof value !== 'object') return false;
  const data = value as Record<string, unknown>;
  return ['research_question', 'method'].every(key => data[key] === null || typeof data[key] === 'string')
    && ['datasets', 'key_results', 'limitations'].every(key => Array.isArray(data[key]) && data[key].every(item => typeof item === 'string'));
}

async function readResponse(response: Response): Promise<OverviewResponse> {
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(typeof data?.detail === 'string' ? data.detail : 'Could not load the overview. Please try again.');
  }
  if (data?.status === 'not_generated' && data.overview === null) return data;
  if (data?.status === 'ready' && isOverview(data.overview)) return data;
  throw new Error('The server returned an invalid overview. Please try again.');
}

function OverviewValue({ value }: { value: string | string[] | null }) {
  if (value === null || (typeof value === 'string' ? !value.trim() : value.length === 0)) {
    return <p className="overview-missing">Not specified in the retrieved context</p>;
  }
  return Array.isArray(value)
    ? <ul>{value.map((item, index) => <li key={index}>{item}</li>)}</ul>
    : <p>{value}</p>;
}

// App keys this component by paper ID; tab switches hide it without unmounting it.
export default function PaperOverview({ paperId, apiUrl }: { paperId: number; apiUrl: string }) {
  const [state, setState] = useState<ViewState>({ status: 'loading' });
  const [reload, setReload] = useState(0);
  const inFlight = useRef(false);
  const generationController = useRef<AbortController | null>(null);
  const endpoint = `${apiUrl}/papers/${paperId}/overview`;

  useEffect(() => {
    const controller = new AbortController();
    inFlight.current = true;
    fetch(endpoint, { signal: controller.signal })
      .then(readResponse)
      .then(data => {
        if (!controller.signal.aborted) {
          setState(data.status === 'ready' ? { status: 'ready', overview: data.overview } : { status: 'empty' });
        }
      })
      .catch(error => {
        if (!controller.signal.aborted) {
          setState({ status: 'error', message: error.message, retry: 'load' });
        }
      })
      .finally(() => { if (!controller.signal.aborted) inFlight.current = false; });
    return () => {
      controller.abort();
      generationController.current?.abort();
    };
  }, [endpoint, reload]);

  const generate = async () => {
    // Synchronous guard also catches clicks before React renders the disabled state.
    if (inFlight.current) return;
    inFlight.current = true;
    const controller = new AbortController();
    generationController.current = controller;
    setState({ status: 'generating' });
    try {
      const response = await fetch(endpoint, { method: 'POST', signal: controller.signal });
      const data = await readResponse(response);
      if (data.status !== 'ready') throw new Error('No overview was generated. Please try again.');
      if (!controller.signal.aborted) setState({ status: 'ready', overview: data.overview });
    } catch (error) {
      if (!controller.signal.aborted) {
        setState({ status: 'error', message: error instanceof Error ? error.message : 'Could not generate the overview. Please try again.', retry: 'generate' });
      }
    } finally {
      if (!controller.signal.aborted) inFlight.current = false;
    }
  };

  const retry = () => {
    if (inFlight.current || state.status !== 'error') return;
    if (state.retry === 'generate') { void generate(); return; }
    inFlight.current = true;
    setState({ status: 'loading' });
    setReload(value => value + 1);
  };

  const busy = state.status === 'loading' || state.status === 'generating';
  return (
    <section className="overview" aria-label="Paper overview" aria-busy={busy}>
      <div className="overview-heading"><h2>Overview</h2>{state.status === 'ready' && <span>Saved</span>}</div>
      {state.status === 'loading' && <div className="overview-state" role="status"><span className="spinner" /><p>Loading overview…</p></div>}
      {(state.status === 'empty' || state.status === 'generating') && (
        <div className="overview-state">
          <h3>Understand this paper</h3>
          <p>Generate a structured overview of the research question, methodology, datasets, results and limitations.</p>
          <button className="primary-button" onClick={() => void generate()} disabled={state.status === 'generating'}>
            {state.status === 'generating' && <span className="spinner" aria-hidden="true" />}
            {state.status === 'generating' ? 'Generating overview…' : 'Generate overview'}
          </button>
          {state.status === 'generating' && <p role="status">Selecting relevant passages and generating the overview. You can use Ask Paper while this runs.</p>}
        </div>
      )}
      {state.status === 'error' && (
        <div className="overview-state overview-error-state">
          <h3>{state.retry === 'generate' ? 'Could not generate overview' : 'Could not load overview'}</h3>
          <p role="alert">{state.message}</p>
          <button className="primary-button" onClick={retry}>Retry</button>
        </div>
      )}
      {state.status === 'ready' && <>
        <dl className="overview-fields">
          <div><dt>Research Question</dt><dd><OverviewValue value={state.overview.research_question} /></dd></div>
          <div><dt>Method</dt><dd><OverviewValue value={state.overview.method} /></dd></div>
          <div><dt>Datasets</dt><dd><OverviewValue value={state.overview.datasets} /></dd></div>
          <div><dt>Key Results</dt><dd><OverviewValue value={state.overview.key_results} /></dd></div>
          <div><dt>Limitations</dt><dd><OverviewValue value={state.overview.limitations} /></dd></div>
        </dl>
        <p className="overview-footnote">Based on selected passages from this paper. Verify findings against the original text.</p>
      </>}
    </section>
  );
}
