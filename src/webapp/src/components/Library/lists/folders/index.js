import React, { useEffect, useState } from "react";
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import {
  CircularProgress,
  Typography,
} from "@mui/material";

import request from '../../../../utils/request';
import FolderList from "./folder-list";

import { ROOT_DIR } from '../../../../config';

const Folders = ({
  musicFilter,
  isSelecting,
  registerMusicToCard,
}) => {
  const { t } = useTranslation();
  const { dir = ROOT_DIR } = useParams();
  const [folders, setFolders] = useState([]);
  const [linkedPaths, setLinkedPaths] = useState(null);
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  const search = ({ name }) => {
    if (musicFilter === '') return true;

    const lowerCaseMusicFilter = musicFilter.toLowerCase();

    return name.toLowerCase().includes(lowerCaseMusicFilter);
  };

  useEffect(() => {
    const fetchFolderList = async () => {
      setIsLoading(true);
      const { result, error } = await request(
        'folderList',
        { folder: decodeURIComponent(dir) }
      );
      setIsLoading(false);

      if(result) setFolders(result);
      if(error) setError(error);
    }

    fetchFolderList();
  }, [dir]);

  useEffect(() => {
    // Load the card database once to badge folders which already have a card linked
    const fetchLinkedPaths = async () => {
      const { result } = await request('cardsList');
      if (!result) return;

      const paths = new Set();
      Object.keys(result).forEach((cardId) => {
        const action = result[cardId]?.action || {};
        const args = [].concat(action.args || []);
        if (typeof args[0] === 'string') paths.add(args[0]);
        ['folder', 'song_url'].forEach((key) => {
          if (typeof action.kwargs?.[key] === 'string') paths.add(action.kwargs[key]);
        });
      });
      setLinkedPaths(paths);
    }

    fetchLinkedPaths();
  }, []);

  const filteredFolders = folders.filter(search);

  if (isLoading) return <CircularProgress />;
  if (error) return <Typography>{t('library.loading-error')}</Typography>;
  if (musicFilter && !filteredFolders.length) {
    return <Typography>{t('library.folders.no-music')}</Typography>;
  }

  return (
    <FolderList
      dir={dir}
      folders={filteredFolders}
      isSelecting={isSelecting}
      linkedPaths={linkedPaths}
      registerMusicToCard={registerMusicToCard}
    />
  );
};

export default Folders;
