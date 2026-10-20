import axios from 'axios'

const chat = axios.create({ baseURL: '/api', timeout: 25000 })
chat.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

export const chatApi = {
  health: () => chat.get('/agent/health').then(r => r.data),
  create: () => chat.post('/chat/sessions').then(r => r.data),
  list: () => chat.get('/chat/sessions').then(r => r.data.items),
  get: id => chat.get(`/chat/sessions/${id}`).then(r => r.data),
  send: (id, body) => chat.post(`/chat/sessions/${id}/messages`, body).then(r => r.data),
  feedback: (id, body) => chat.post(`/chat/sessions/${id}/feedback`, body).then(r => r.data),
  event: body => chat.post('/recommendation-events', body).then(r => r.data),
  login: (email, password) => chat.post('/auth/login', { email, password }).then(r => r.data),
  profile: () => chat.get('/users/me').then(r => r.data),
  catalog: () => chat.get('/movies', { params: { page_size: 8, sort_by: 'rating', min_rating: 7 } }).then(r => r.data.items),
}
