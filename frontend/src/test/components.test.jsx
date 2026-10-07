import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import DocumentUpload from '../components/DocumentUpload';
import CameraCapture from '../components/CameraCapture';

describe('document consent and validation', () => {
  it('requires a valid file and consent before submitting', () => {
    URL.createObjectURL = vi.fn(() => 'blob:preview');
    URL.revokeObjectURL = vi.fn();
    const submit = vi.fn();
    render(<DocumentUpload onSubmit={submit} busy={false}/>);
    const button = screen.getByRole('button', {name: /Analyze document/});
    expect(button).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Select document photo'), {target: {files: [new File(['x'], 'id.pdf', {type:'application/pdf'})]}});
    expect(screen.getByRole('alert')).toHaveTextContent('JPEG');
    fireEvent.change(screen.getByLabelText('Select document photo'), {target: {files: [new File(['jpeg'], 'id.jpg', {type:'image/jpeg'})]}});
    expect(button).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox'));
    expect(button).toBeEnabled();
    fireEvent.click(button);
    expect(submit).toHaveBeenCalledOnce();
  });
});

describe('camera permission lifecycle', () => {
  it('explains permission denial', async () => {
    Object.defineProperty(window, 'isSecureContext', {value: true, configurable: true});
    Object.defineProperty(navigator, 'mediaDevices', {value: {getUserMedia: vi.fn().mockRejectedValue(new DOMException('Denied', 'NotAllowedError'))}, configurable: true});
    render(<CameraCapture session={{mode:'demo'}} onComplete={vi.fn()} onRestart={vi.fn()}/>);
    expect(await screen.findByRole('alert')).toHaveTextContent('Camera access was denied');
  });
  it('stops the camera if permission resolves after unmount', async () => {
    Object.defineProperty(window, 'isSecureContext', {value: true, configurable: true});
    let resolve;
    const stop = vi.fn();
    Object.defineProperty(navigator, 'mediaDevices', {value: {getUserMedia: vi.fn(() => new Promise(done => {resolve=done;}))}, configurable: true});
    const {unmount} = render(<CameraCapture session={{mode:'demo'}} onComplete={vi.fn()} onRestart={vi.fn()}/>);
    unmount();
    resolve({getTracks: () => [{stop}]});
    await new Promise(done => setTimeout(done, 0));
    expect(stop).toHaveBeenCalledOnce();
  });
});
