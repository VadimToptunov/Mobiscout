//
//  EventExporter.swift
//  MobiscoutSDK
//
//  Exports captured events to JSON files
//

import Foundation

/// Exports events to JSON files
public class EventExporter {
    
    // MARK: - Configuration
    
    public struct ExportConfig {
        public let bufferSize: Int
        public let maxStoredFiles: Int
        public let exportIntervalMs: Int64
        
        public init(
            bufferSize: Int = 500,
            maxStoredFiles: Int = 10,
            exportIntervalMs: Int64 = 30000
        ) {
            self.bufferSize = bufferSize
            self.maxStoredFiles = maxStoredFiles
            self.exportIntervalMs = exportIntervalMs
        }
    }
    
    // MARK: - Properties
    
    private let config: ExportConfig
    private var isRunning = false
    
    private var eventBuffer: [Event] = []
    private let bufferQueue = DispatchQueue(label: "com.mobiscout.eventexporter.buffer")
    
    private var exportTimer: Timer?
    private var eventCount = 0
    private var lastExportTime: Date = Date()
    
    // MARK: - Initializer
    
    public init(config: ExportConfig) {
        self.config = config
    }
    
    // MARK: - Public API
    
    /// Start exporter
    public func start() {
        guard !isRunning else {
            print("[EventExporter] Already running")
            return
        }
        
        print("[EventExporter] Starting...")
        isRunning = true
        
        // Start periodic export timer
        startPeriodicExport()
        
        print("[EventExporter] Started")
    }
    
    /// Stop exporter and flush remaining events
    public func stop() {
        guard isRunning else {
            print("[EventExporter] Not running")
            return
        }
        
        print("[EventExporter] Stopping...")
        
        // Stop timer
        exportTimer?.invalidate()
        exportTimer = nil
        
        // Flush remaining events
        bufferQueue.sync {
            if !eventBuffer.isEmpty {
                exportEvents()
            }
        }
        
        isRunning = false
        print("[EventExporter] Stopped. Exported \(eventCount) events total")
    }
    
    /// Queue an event for export
    /// - Parameter event: Event to queue
    public func queueEvent(_ event: Event) {
        guard isRunning else { return }
        
        bufferQueue.async { [weak self] in
            guard let self = self else { return }
            
            self.eventBuffer.append(event)
            self.eventCount += 1
            
            // Export if buffer is full
            if self.eventBuffer.count >= self.config.bufferSize {
                self.exportEvents()
            }
        }
    }
    
    // MARK: - Private Methods
    
    private func startPeriodicExport() {
        let interval = TimeInterval(config.exportIntervalMs) / 1000.0
        
        exportTimer = Timer.scheduledTimer(withTimeInterval: interval, repeats: true) { [weak self] _ in
            self?.periodicExport()
        }
    }
    
    private func periodicExport() {
        bufferQueue.async { [weak self] in
            guard let self = self else { return }
            
            let timeSinceLastExport = Date().timeIntervalSince(self.lastExportTime)
            let intervalSeconds = TimeInterval(self.config.exportIntervalMs) / 1000.0
            
            if !self.eventBuffer.isEmpty && timeSinceLastExport >= intervalSeconds {
                print("[EventExporter] Periodic export triggered (\(self.eventBuffer.count) events)")
                self.exportEvents()
            }
        }
    }
    
    private func exportEvents() {
        guard !eventBuffer.isEmpty else { return }
        
        let eventsToExport = eventBuffer
        eventBuffer.removeAll()
        lastExportTime = Date()
        
        // Generate filename with millisecond precision
        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyyMMdd_HHmmss_SSS"
        let timestamp = dateFormatter.string(from: Date())
        let filename = "observe_events_\(timestamp).json"
        
        // Get export directory
        guard let exportDir = getExportDirectory() else {
            print("[EventExporter] Failed to get export directory")
            return
        }
        
        let fileURL = exportDir.appendingPathComponent(filename)
        
        // Serialize events to JSON
        do {
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            
            // Wrap events in a container
            let container: [String: Any] = [
                "session_id": MobiscoutSDK.shared.getSession()?.sessionId ?? "unknown",
                "export_time": Int64(Date().timeIntervalSince1970 * 1000),
                "event_count": eventsToExport.count,
                "events": try eventsToExport.map { event -> [String: Any] in
                    let data = try encoder.encode(event)
                    return try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
                }
            ]
            
            let jsonData = try JSONSerialization.data(withJSONObject: container, options: [.prettyPrinted])
            try jsonData.write(to: fileURL)
            
            print("[EventExporter] Exported \(eventsToExport.count) events to: \(filename)")
            
            // Cleanup old files
            cleanupOldFiles(in: exportDir)
            
        } catch {
            print("[EventExporter] Failed to export events: \(error)")
        }
    }
    
    private func getExportDirectory() -> URL? {
        guard let documentsDir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else {
            return nil
        }
        
        let exportDir = documentsDir.appendingPathComponent("mobiscout")
        
        // Create directory if it doesn't exist
        if !FileManager.default.fileExists(atPath: exportDir.path) {
            do {
                try FileManager.default.createDirectory(at: exportDir, withIntermediateDirectories: true)
            } catch {
                print("[EventExporter] Failed to create export directory: \(error)")
                return nil
            }
        }
        
        return exportDir
    }
    
    private func cleanupOldFiles(in directory: URL) {
        do {
            let files = try FileManager.default.contentsOfDirectory(
                at: directory,
                includingPropertiesForKeys: [.creationDateKey],
                options: [.skipsHiddenFiles]
            )
            
            // Sort by creation date (oldest first)
            let sortedFiles = files.sorted { file1, file2 in
                let date1 = try? file1.resourceValues(forKeys: [.creationDateKey]).creationDate ?? Date.distantPast
                let date2 = try? file2.resourceValues(forKeys: [.creationDateKey]).creationDate ?? Date.distantPast
                return (date1 ?? Date.distantPast) < (date2 ?? Date.distantPast)
            }
            
            // Delete oldest files if exceeding max
            if sortedFiles.count > config.maxStoredFiles {
                let filesToDelete = sortedFiles.prefix(sortedFiles.count - config.maxStoredFiles)
                for file in filesToDelete {
                    try? FileManager.default.removeItem(at: file)
                    print("[EventExporter] Deleted old file: \(file.lastPathComponent)")
                }
            }
            
        } catch {
            print("[EventExporter] Failed to cleanup old files: \(error)")
        }
    }
}

