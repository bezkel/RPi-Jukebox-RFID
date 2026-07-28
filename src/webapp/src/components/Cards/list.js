import React, { forwardRef, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { isNil, reject } from 'ramda';
import { useTranslation } from 'react-i18next';

import {
  Avatar,
  Grid,
  InputAdornment,
  List,
  ListItem,
  ListItemAvatar,
  ListItemText,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography
} from '@mui/material';

import BookmarkIcon from '@mui/icons-material/Bookmark';
import SearchIcon from '@mui/icons-material/Search';

const CardsList = ({ cardsList }) => {
  const { t } = useTranslation();
  const [cardsFilter, setCardsFilter] = useState('');
  const [sortBy, setSortBy] = useState('content');

  // Flatten the cards object into a searchable and sortable list
  const entries = useMemo(() => {
    const list = Object.keys(cardsList || {}).map((cardId) => {
      const card = cardsList[cardId];
      const description = card.from_alias
        ? reject(isNil, [card.from_alias, card.action?.args]).join(', ')
        : card.func;
      // Sort/search key without the alias prefix: the actual content (folder, album, ...)
      const content = card.action?.args
        ? [].concat(card.action.args).join(' ')
        : (card.func || '');

      return { cardId, description, content };
    });

    const query = cardsFilter.trim().toLowerCase();
    const filtered = query
      ? list.filter(({ cardId, description }) => (
          cardId.toLowerCase().includes(query) ||
          (description || '').toLowerCase().includes(query)
        ))
      : list;

    return filtered.sort((a, b) => (
      sortBy === 'id'
        ? a.cardId.localeCompare(b.cardId, undefined, { numeric: true })
        : (a.content || '').localeCompare(b.content || '', undefined, { sensitivity: 'base' })
    ));
  }, [cardsList, cardsFilter, sortBy]);

  const ListItemLink = ({ cardId, description }) => {
    const EditCardLink = forwardRef((props, ref) => {
      const { data } = props;
      const location = {
        pathname: `/cards/${data.id}/edit`,
        state: data,
      };

      return <Link ref={ref} to={location} {...props} />
    });

    return (
      <ListItem
        button
        component={EditCardLink}
        data={{ id: cardId, ...cardsList[cardId] }}
        key={cardId}
      >
        <ListItemAvatar>
          <Avatar>
            <BookmarkIcon />
          </Avatar>
        </ListItemAvatar>
        <ListItemText
          primary={cardId}
          secondary={description}
        />
      </ListItem>
    );
  }

  if (!cardsList || Object.keys(cardsList).length === 0) {
    return <Typography>{t('cards.list.no-cards-registered')}</Typography>;
  }

  return (
    <Grid container sx={{ width: '100%' }}>
      <Grid
        container
        sx={{
          alignItems: 'center',
          gap: 1,
          padding: '10px 15px 0 15px',
        }}
      >
        <TextField
          label={t('cards.list.search-label')}
          onChange={(event) => setCardsFilter(event.target.value)}
          size="small"
          sx={{ flexGrow: 1 }}
          value={cardsFilter}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" />
              </InputAdornment>
            ),
          }}
        />
        <ToggleButtonGroup
          aria-label={t('cards.list.sort-label')}
          exclusive
          onChange={(event, value) => value && setSortBy(value)}
          size="small"
          value={sortBy}
        >
          <ToggleButton value="content">{t('cards.list.sort-by-content')}</ToggleButton>
          <ToggleButton value="id">{t('cards.list.sort-by-id')}</ToggleButton>
        </ToggleButtonGroup>
      </Grid>
      {entries.length === 0
        ? <Typography sx={{ padding: '15px' }}>{t('cards.list.no-cards-found')}</Typography>
        : <List sx={{ width: '100%' }}>
            {entries.map(ListItemLink)}
          </List>
      }
    </Grid>
  );
}

export default React.memo(CardsList);
