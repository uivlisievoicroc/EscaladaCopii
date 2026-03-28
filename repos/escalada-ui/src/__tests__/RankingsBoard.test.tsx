import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import RankingsBoard, { type PublicBox } from '../components/RankingsBoard';

vi.mock('../utilis/sanitize', () => ({
  sanitizeBoxName: (text: string) => text,
  sanitizeCompetitorName: (text: string) => text,
}));

describe('RankingsBoard score display', () => {
  it('renders .1 as plus and keeps TOP/int/other decimals unchanged', () => {
    const box: PublicBox = {
      boxId: 0,
      categorie: 'Seniori',
      initiated: true,
      routeIndex: 1,
      routesCount: 1,
      holdsCount: 20,
      holdsCounts: [20],
      timeCriterionEnabled: false,
      leadRankingRows: [
        {
          name: 'Cara',
          rank: 1,
          score: 20,
          total: 20,
          raw_scores: [20],
          raw_times: [null],
          tb_time: false,
          tb_prev: false,
        },
        {
          name: 'Dan',
          rank: 2,
          score: 12.5,
          total: 12.5,
          raw_scores: [12.5],
          raw_times: [null],
          tb_time: false,
          tb_prev: false,
        },
        {
          name: 'Ana',
          rank: 3,
          score: 9.1,
          total: 9.1,
          raw_scores: [9.1],
          raw_times: [null],
          tb_time: false,
          tb_prev: false,
        },
        {
          name: 'Bob',
          rank: 4,
          score: 9.0,
          total: 9.0,
          raw_scores: [9.0],
          raw_times: [null],
          tb_time: false,
          tb_prev: false,
        },
      ],
    };

    render(
      <RankingsBoard
        boxes={{ 0: box }}
        selectedBoxId={0}
        setSelectedBoxId={vi.fn()}
      />,
    );

    const anaRow = screen.getByText('Ana').closest('div[class*="grid"]');
    const bobRow = screen.getByText('Bob').closest('div[class*="grid"]');
    const caraRow = screen.getByText('Cara').closest('div[class*="grid"]');
    const danRow = screen.getByText('Dan').closest('div[class*="grid"]');

    expect(anaRow).not.toBeNull();
    expect(bobRow).not.toBeNull();
    expect(caraRow).not.toBeNull();
    expect(danRow).not.toBeNull();

    if (anaRow && bobRow && caraRow && danRow) {
      expect(within(anaRow).getByText('9+')).toBeInTheDocument();
      expect(within(bobRow).getByText(/^9$/)).toBeInTheDocument();
      expect(within(caraRow).getByText('TOP')).toBeInTheDocument();
      expect(within(danRow).getByText('12.5')).toBeInTheDocument();
      expect(within(bobRow).queryByText('9.0')).not.toBeInTheDocument();
    }
  });
});
