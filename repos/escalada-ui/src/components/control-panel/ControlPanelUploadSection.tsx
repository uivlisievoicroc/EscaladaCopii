import React, { FC } from 'react';
import ModalUpload from '../ModalUpload';
import type { Competitor } from '../../types';

type UploadedListbox = {
  categorie: string;
  concurenti: Competitor[];
  routesCount?: number | string;
  holdsCounts?: Array<number | string>;
};

type Props = {
  isOpen: boolean;
  disabled: boolean;
  onClose: () => void;
  onUpload: (data: UploadedListbox) => void;
};

const ControlPanelUploadSection: FC<Props> = ({ isOpen, disabled, onClose, onUpload }) => (
  <div className="space-y-4">
    <div className="grid grid-cols-[repeat(1,minmax(320px,560px))] gap-3">
      <ModalUpload isOpen={isOpen} embedded disabled={disabled} onClose={onClose} onUpload={onUpload} />
    </div>
  </div>
);

export default ControlPanelUploadSection;
