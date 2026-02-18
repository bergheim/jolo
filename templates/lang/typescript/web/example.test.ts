import { describe, it, expect } from 'bun:test';
import { app } from './index';

describe('BETH App', () => {
  it('should have a healthy status', async () => {
    const res = await app.handle(new Request('http://localhost/health'));
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ status: 'ok' });
  });

  it('should greet the user via API', async () => {
    const res = await app.handle(new Request('http://localhost/api/hello?name=BETH'));
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ message: 'Hello, BETH!' });
  });

  it('should serve the home page', async () => {
    const res = await app.handle(new Request('http://localhost/'));
    expect(res.status).toBe(200);
    expect(res.headers.get('content-type')).toContain('text/html');
    const html = await res.text();
    expect(html).toContain('BETH Stack Scaffold');
  });
});
