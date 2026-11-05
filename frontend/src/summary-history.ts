import type { AiSummaryJob, SavedSummary } from './summary-types'
import type { VideoInfo } from './types'

const DB_NAME = 'shizhen-ai-summaries'
const STORE_NAME = 'summaries'
const DB_VERSION = 1
const MAX_RECORDS = 30

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('IndexedDB 请求失败'))
  })
}

function openDatabase(): Promise<IDBDatabase> {
  if (!globalThis.indexedDB) {
    return Promise.reject(new Error('当前浏览器不支持本地摘要记录'))
  }
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)
    request.onupgradeneeded = () => {
      const database = request.result
      if (!database.objectStoreNames.contains(STORE_NAME)) {
        const store = database.createObjectStore(STORE_NAME, { keyPath: 'id' })
        store.createIndex('savedAt', 'savedAt')
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('无法打开本地摘要记录'))
  })
}

export async function listSavedSummaries(): Promise<SavedSummary[]> {
  const database = await openDatabase()
  try {
    const transaction = database.transaction(STORE_NAME, 'readonly')
    const records = await requestResult(
      transaction.objectStore(STORE_NAME).getAll() as IDBRequest<SavedSummary[]>,
    )
    return records.sort((left, right) => right.savedAt.localeCompare(left.savedAt))
  } finally {
    database.close()
  }
}

export async function saveSummary(video: VideoInfo, job: AiSummaryJob): Promise<SavedSummary> {
  if (!job.result) {
    throw new Error('摘要尚未生成完成')
  }
  const record: SavedSummary = {
    id: job.job_id,
    videoUrl: video.url,
    videoTitle: video.title,
    thumbnail: video.thumbnail,
    durationSeconds: video.duration_seconds,
    savedAt: new Date().toISOString(),
    result: job.result,
  }

  const database = await openDatabase()
  try {
    const transaction = database.transaction(STORE_NAME, 'readwrite')
    const store = transaction.objectStore(STORE_NAME)
    const existing = await requestResult(store.getAll() as IDBRequest<SavedSummary[]>)
    store.put(record)
    const overflow = existing
      .sort((left, right) => left.savedAt.localeCompare(right.savedAt))
      .slice(0, Math.max(0, existing.length - MAX_RECORDS + 1))
    for (const item of overflow) {
      store.delete(item.id)
    }
    await new Promise<void>((resolve, reject) => {
      transaction.oncomplete = () => resolve()
      transaction.onerror = () => reject(transaction.error ?? new Error('保存摘要失败'))
      transaction.onabort = () => reject(transaction.error ?? new Error('保存摘要已中止'))
    })
  } finally {
    database.close()
  }
  return record
}

export async function deleteSavedSummary(id: string): Promise<void> {
  const database = await openDatabase()
  try {
    const transaction = database.transaction(STORE_NAME, 'readwrite')
    transaction.objectStore(STORE_NAME).delete(id)
    await new Promise<void>((resolve, reject) => {
      transaction.oncomplete = () => resolve()
      transaction.onerror = () => reject(transaction.error ?? new Error('删除摘要失败'))
    })
  } finally {
    database.close()
  }
}

export async function clearSavedSummaries(): Promise<void> {
  const database = await openDatabase()
  try {
    const transaction = database.transaction(STORE_NAME, 'readwrite')
    transaction.objectStore(STORE_NAME).clear()
    await new Promise<void>((resolve, reject) => {
      transaction.oncomplete = () => resolve()
      transaction.onerror = () => reject(transaction.error ?? new Error('清空摘要失败'))
    })
  } finally {
    database.close()
  }
}
