import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AdminMessages from './AdminMessages';

vi.mock('../api/systemMessages', () => ({
  listAllMessages: vi.fn(),
  createMessage: vi.fn(),
  updateMessage: vi.fn(),
  deleteMessage: vi.fn(),
}));

import {
  listAllMessages,
  createMessage,
  updateMessage,
  deleteMessage,
} from '../api/systemMessages';

beforeEach(() => {
  listAllMessages.mockReset();
  createMessage.mockReset();
  updateMessage.mockReset();
  deleteMessage.mockReset();
  listAllMessages.mockResolvedValue([]);
});

describe('AdminMessages — list rendering', () => {
  it('renders the page header', async () => {
    render(<AdminMessages />);
    expect(screen.getByText('System Messages')).toBeInTheDocument();
    await waitFor(() => expect(listAllMessages).toHaveBeenCalled());
  });

  it('shows "No messages yet." for an empty list', async () => {
    render(<AdminMessages />);
    await waitFor(() => {
      expect(screen.getByText('No messages yet.')).toBeInTheDocument();
    });
  });

  it('lists every message including deleted/expired', async () => {
    listAllMessages.mockResolvedValue([
      { id: 'a', title: 'Active item', body: 'b', category: 'info', pinned: false, published_at: '2026-06-14T20:00:00Z' },
      { id: 'b', title: 'Old item', body: 'b', category: 'info', pinned: false, published_at: '2026-06-13T20:00:00Z', deleted_at: '2026-06-14T00:00:00Z' },
    ]);
    render(<AdminMessages />);
    await waitFor(() => {
      expect(screen.getByText('Active item')).toBeInTheDocument();
    });
    expect(screen.getByText('Old item')).toBeInTheDocument();
    // The badge for the soft-deleted item is present
    expect(screen.getByText('Deleted')).toBeInTheDocument();
  });

  it('shows error when load fails', async () => {
    listAllMessages.mockRejectedValue(new Error('boom'));
    render(<AdminMessages />);
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/boom/),
    );
  });
});

describe('AdminMessages — compose', () => {
  it('Post button is disabled when title and body are empty', async () => {
    render(<AdminMessages />);
    const post = await screen.findByRole('button', { name: 'Post' });
    expect(post).toBeDisabled();
  });

  it('submitting the compose form calls createMessage with the form values', async () => {
    createMessage.mockResolvedValue({ id: 'new' });
    listAllMessages
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        { id: 'new', title: 'Patch tonight', body: 'See you', category: 'maintenance', pinned: true, published_at: '2026-06-14T20:00:00Z' },
      ]);
    render(<AdminMessages />);
    await screen.findByText('No messages yet.');

    await userEvent.type(screen.getByLabelText(/Title/i), 'Patch tonight');
    await userEvent.type(screen.getByLabelText(/Body/i), 'See you');
    // Category select default is 'info'; flip to maintenance
    await userEvent.selectOptions(screen.getByLabelText(/Category/i), 'maintenance');
    await userEvent.click(screen.getByLabelText(/Pinned/i));
    await userEvent.click(screen.getByRole('button', { name: 'Post' }));

    await waitFor(() => expect(createMessage).toHaveBeenCalledTimes(1));
    const call = createMessage.mock.calls[0][0];
    expect(call.title).toBe('Patch tonight');
    expect(call.body).toBe('See you');
    expect(call.category).toBe('maintenance');
    expect(call.pinned).toBe(true);
  });
});

describe('AdminMessages — actions', () => {
  it('clicking Pin calls updateMessage with the toggled pinned value', async () => {
    listAllMessages
      .mockResolvedValueOnce([
        { id: 'a', title: 'M', body: 'b', category: 'info', pinned: false, published_at: '2026-06-14T20:00:00Z' },
      ])
      .mockResolvedValueOnce([
        { id: 'a', title: 'M', body: 'b', category: 'info', pinned: true, published_at: '2026-06-14T20:00:00Z' },
      ]);
    updateMessage.mockResolvedValue({});
    render(<AdminMessages />);
    const pinBtn = await screen.findByRole('button', { name: 'Pin' });
    await userEvent.click(pinBtn);
    expect(updateMessage).toHaveBeenCalledWith('a', { pinned: true });
  });

  it('clicking Delete confirms then calls deleteMessage', async () => {
    listAllMessages
      .mockResolvedValueOnce([
        { id: 'a', title: 'M', body: 'b', category: 'info', pinned: false, published_at: '2026-06-14T20:00:00Z' },
      ])
      .mockResolvedValueOnce([]);
    deleteMessage.mockResolvedValue({});
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<AdminMessages />);
    const delBtn = await screen.findByRole('button', { name: 'Delete' });
    await userEvent.click(delBtn);
    expect(deleteMessage).toHaveBeenCalledWith('a');
    confirmSpy.mockRestore();
  });

  it('Delete does nothing when the confirm dialog is cancelled', async () => {
    listAllMessages.mockResolvedValue([
      { id: 'a', title: 'M', body: 'b', category: 'info', pinned: false, published_at: '2026-06-14T20:00:00Z' },
    ]);
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(<AdminMessages />);
    const delBtn = await screen.findByRole('button', { name: 'Delete' });
    await userEvent.click(delBtn);
    expect(deleteMessage).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});
