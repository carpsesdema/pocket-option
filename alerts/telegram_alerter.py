"""
Telegram alert system for ZigZag Detector
Handles sending alerts and managing notification settings
"""

import requests
import logging
import time
import threading
import queue
from typing import List, Dict, Optional
from datetime import datetime
import json
import os


class TelegramAlerter:
    """Handles Telegram alerts for crossover detection"""

    def __init__(self, config_manager):
        self.config = config_manager
        self.alert_queue = queue.Queue()
        self.last_alert_time = 0
        self.failed_alerts = []
        self.bot_info = None
        self.worker_thread = None
        self.running = False

    def start_worker(self):
        """Start background worker thread for sending alerts"""
        if not self.worker_thread or not self.worker_thread.is_alive():
            self.running = True
            self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self.worker_thread.start()
            logging.info("Telegram alert worker started")

    def stop_worker(self):
        """Stop background worker thread"""
        self.running = False
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=5)
            logging.info("Telegram alert worker stopped")

    def _worker_loop(self):
        """Background worker loop for processing alert queue"""
        while self.running:
            try:
                # Get alert from queue with timeout
                alert_data = self.alert_queue.get(timeout=1)

                # Send alert
                success = self._send_telegram_message(
                    alert_data['message'],
                    alert_data.get('parse_mode', 'HTML')
                )

                if success:
                    self.last_alert_time = time.time()
                    logging.info("Alert sent successfully")
                else:
                    self.failed_alerts.append({
                        'timestamp': time.time(),
                        'message': alert_data['message'],
                        'error': 'Send failed'
                    })

                self.alert_queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                logging.error(f"Alert worker error: {e}")

    def test_connection(self) -> tuple[bool, str]:
        """Test Telegram bot connection"""
        try:
            token = self.config.get('alerts', 'telegram_token', '')
            if not token:
                return False, "No Telegram token configured"

            # Test bot info
            url = f"https://api.telegram.org/bot{token}/getMe"
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data.get('ok'):
                    self.bot_info = data.get('result', {})
                    bot_name = self.bot_info.get('username', 'Unknown')
                    return True, f"Connected to bot: @{bot_name}"
                else:
                    error_desc = data.get('description', 'Unknown error')
                    return False, f"Bot API error: {error_desc}"
            else:
                return False, f"HTTP error: {response.status_code}"

        except requests.exceptions.Timeout:
            return False, "Connection timeout"
        except requests.exceptions.RequestException as e:
            return False, f"Network error: {e}"
        except Exception as e:
            return False, f"Unexpected error: {e}"

    def test_chat(self) -> tuple[bool, str]:
        """Test sending message to configured chat"""
        try:
            chat_id = self.config.get('alerts', 'telegram_chat_id', '')
            if not chat_id:
                return False, "No chat ID configured"

            test_message = "🔧 ZigZag Detector Test Message\n\nIf you see this, alerts are working correctly!"

            success = self._send_telegram_message(test_message)

            if success:
                return True, "Test message sent successfully"
            else:
                return False, "Failed to send test message"

        except Exception as e:
            return False, f"Test failed: {e}"

    def send_crossover_alert(self, crossover) -> bool:
        """Queue crossover alert for sending"""
        try:
            if not self.config.get('alerts', 'telegram_enabled', True):
                return False

            # Check cooldown
            cooldown = self.config.get('alerts', 'cooldown_seconds', 300)
            if time.time() - self.last_alert_time < cooldown:
                logging.info(f"Alert skipped due to cooldown ({cooldown}s)")
                return False

            # Format alert message
            message = self._format_crossover_message(crossover)

            # Add to queue
            self.alert_queue.put({
                'message': message,
                'parse_mode': 'HTML'
            })

            # Start worker if not running
            if not self.running:
                self.start_worker()

            return True

        except Exception as e:
            logging.error(f"Failed to queue alert: {e}")
            return False

    def _send_telegram_message(self, message: str, parse_mode: str = 'HTML') -> bool:
        """Send message via Telegram API"""
        try:
            token = self.config.get('alerts', 'telegram_token', '')
            chat_id = self.config.get('alerts', 'telegram_chat_id', '')

            if not token or not chat_id:
                logging.error("Telegram token or chat ID not configured")
                return False

            url = f"https://api.telegram.org/bot{token}/sendMessage"
            data = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': parse_mode,
                'disable_web_page_preview': True
            }

            response = requests.post(url, data=data, timeout=15)

            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    return True
                else:
                    error_desc = result.get('description', 'Unknown error')
                    logging.error(f"Telegram API error: {error_desc}")
                    return False
            else:
                logging.error(f"HTTP error: {response.status_code}")
                return False

        except requests.exceptions.Timeout:
            logging.error("Telegram request timeout")
            return False
        except requests.exceptions.RequestException as e:
            logging.error(f"Telegram network error: {e}")
            return False
        except Exception as e:
            logging.error(f"Telegram send error: {e}")
            return False

    def _format_crossover_message(self, crossover) -> str:
        """Format crossover detection message"""
        try:
            timestamp = datetime.fromtimestamp(crossover.timestamp).strftime("%H:%M:%S")

            # Determine signal strength emoji
            confidence = crossover.combined_confidence
            if confidence > 0.9:
                strength_emoji = "🔥🔥🔥"
                strength_text = "STRONG"
            elif confidence > 0.8:
                strength_emoji = "🔥🔥"
                strength_text = "GOOD"
            elif confidence > 0.7:
                strength_emoji = "🔥"
                strength_text = "MODERATE"
            else:
                strength_emoji = "⚠️"
                strength_text = "WEAK"

            # Line names for display
            line1_display = crossover.line1_name.replace('zigzag_', '').replace('_', ' ').title()
            line2_display = crossover.line2_name.replace('zigzag_', '').replace('_', ' ').title()

            message = f"""
{strength_emoji} <b>ZigZag Crossover Detected!</b>

📊 <b>Signal Strength:</b> {strength_text} ({confidence:.1%})
🎯 <b>Lines:</b> {line1_display} ↔ {line2_display}
📍 <b>Position:</b> ({crossover.intersection_point[0]}, {crossover.intersection_point[1]})
📐 <b>Angle:</b> {crossover.angle:.1f}°
⏰ <b>Time:</b> {timestamp}

🚀 <b>Trade Opportunity!</b>
💡 Review your strategy and consider entry
            """.strip()

            return message

        except Exception as e:
            logging.error(f"Failed to format message: {e}")
            return f"ZigZag Crossover detected at {crossover.intersection_point}"

    def send_status_update(self, status_data: Dict) -> bool:
        """Send system status update"""
        try:
            if not self.config.get('alerts', 'telegram_enabled', True):
                return False

            message = self._format_status_message(status_data)

            self.alert_queue.put({
                'message': message,
                'parse_mode': 'HTML'
            })

            if not self.running:
                self.start_worker()

            return True

        except Exception as e:
            logging.error(f"Failed to send status update: {e}")
            return False

    def _format_status_message(self, status_data: Dict) -> str:
        """Format system status message"""
        try:
            current_time = datetime.now().strftime("%H:%M:%S")

            lines_detected = status_data.get('lines_detected', 0)
            crossovers_today = status_data.get('crossovers_today', 0)
            system_uptime = status_data.get('uptime_hours', 0)

            message = f"""
📊 <b>ZigZag Detector Status</b>

⏰ <b>Time:</b> {current_time}
🔍 <b>Lines Detected:</b> {lines_detected}
📈 <b>Crossovers Today:</b> {crossovers_today}
⏳ <b>Uptime:</b> {system_uptime:.1f} hours

✅ System running normally
            """.strip()

            return message

        except Exception as e:
            logging.error(f"Failed to format status message: {e}")
            return f"System status update at {datetime.now().strftime('%H:%M:%S')}"

    def get_alert_statistics(self) -> Dict:
        """Get alert sending statistics"""
        try:
            current_time = time.time()

            # Count failed alerts in last 24 hours
            recent_failures = sum(1 for alert in self.failed_alerts
                                  if current_time - alert['timestamp'] < 86400)

            return {
                'queue_size': self.alert_queue.qsize(),
                'last_alert_time': self.last_alert_time,
                'failed_alerts_24h': recent_failures,
                'total_failures': len(self.failed_alerts),
                'worker_running': self.running,
                'bot_username': self.bot_info.get('username', 'Unknown') if self.bot_info else 'Not connected'
            }

        except Exception as e:
            logging.error(f"Failed to get alert statistics: {e}")
            return {}

    def cleanup_failed_alerts(self):
        """Clean up old failed alert records"""
        try:
            current_time = time.time()
            retention_time = 86400 * 7  # Keep for 1 week

            self.failed_alerts = [
                alert for alert in self.failed_alerts
                if current_time - alert['timestamp'] < retention_time
            ]

        except Exception as e:
            logging.error(f"Failed to cleanup alerts: {e}")


class AlertManager:
    """Manages multiple alert channels"""

    def __init__(self, config_manager):
        self.config = config_manager
        self.telegram = TelegramAlerter(config_manager)
        self.alert_history = []

    def send_crossover_alert(self, crossover) -> Dict[str, bool]:
        """Send crossover alert through all enabled channels"""
        results = {}

        try:
            # Telegram alerts
            if self.config.get('alerts', 'telegram_enabled', True):
                results['telegram'] = self.telegram.send_crossover_alert(crossover)

            # Sound alerts (if enabled)
            if self.config.get('alerts', 'sound_enabled', True):
                results['sound'] = self._play_alert_sound()

            # Popup alerts (if enabled)
            if self.config.get('alerts', 'popup_enabled', False):
                results['popup'] = self._show_popup_alert(crossover)

            # Log to file (if enabled)
            if self.config.get('alerts', 'log_file_enabled', True):
                results['log_file'] = self._log_to_file(crossover)

            # Add to history
            self.alert_history.append({
                'timestamp': time.time(),
                'crossover': crossover,
                'results': results
            })

            # Cleanup old history
            self._cleanup_history()

        except Exception as e:
            logging.error(f"Alert manager error: {e}")
            results['error'] = str(e)

        return results

    def _play_alert_sound(self) -> bool:
        """Play alert sound"""
        try:
            # Try to play system beep
            import winsound
            winsound.Beep(1000, 500)  # 1000 Hz for 500ms
            return True
        except ImportError:
            # Fallback for non-Windows systems
            try:
                print('\a')  # Terminal bell
                return True
            except:
                return False
        except Exception as e:
            logging.error(f"Sound alert failed: {e}")
            return False

    def _show_popup_alert(self, crossover) -> bool:
        """Show popup alert (placeholder)"""
        # This would show a system notification or popup window
        # Implementation depends on platform and requirements
        try:
            logging.info(f"Popup alert: Crossover detected at {crossover.intersection_point}")
            return True
        except Exception as e:
            logging.error(f"Popup alert failed: {e}")
            return False

    def _log_to_file(self, crossover) -> bool:
        """Log crossover to file"""
        try:
            log_dir = 'logs'
            os.makedirs(log_dir, exist_ok=True)

            log_file = os.path.join(log_dir, 'crossover_alerts.log')

            timestamp = datetime.fromtimestamp(crossover.timestamp).strftime("%Y-%m-%d %H:%M:%S")
            log_entry = {
                'timestamp': timestamp,
                'line1': crossover.line1_name,
                'line2': crossover.line2_name,
                'position': crossover.intersection_point,
                'confidence': crossover.combined_confidence,
                'angle': crossover.angle
            }

            with open(log_file, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')

            return True

        except Exception as e:
            logging.error(f"File logging failed: {e}")
            return False

    def _cleanup_history(self):
        """Clean up old alert history"""
        try:
            current_time = time.time()
            retention_time = 86400 * 7  # Keep for 1 week

            self.alert_history = [
                alert for alert in self.alert_history
                if current_time - alert['timestamp'] < retention_time
            ]

        except Exception as e:
            logging.error(f"History cleanup failed: {e}")

    def get_statistics(self) -> Dict:
        """Get alert statistics"""
        try:
            current_time = time.time()

            # Count alerts in different time periods
            last_hour = sum(1 for alert in self.alert_history
                            if current_time - alert['timestamp'] < 3600)
            last_day = sum(1 for alert in self.alert_history
                           if current_time - alert['timestamp'] < 86400)

            # Get Telegram statistics
            telegram_stats = self.telegram.get_alert_statistics()

            return {
                'total_alerts': len(self.alert_history),
                'last_hour': last_hour,
                'last_day': last_day,
                'telegram': telegram_stats
            }

        except Exception as e:
            logging.error(f"Failed to get alert statistics: {e}")
            return {}