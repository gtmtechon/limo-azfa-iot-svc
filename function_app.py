# function_app.py

import logging
import json
import os
import azure.functions as func

# SendGrid 라이브러리 임포트 (MaintenanceScheduler 함수에 필요)
# 본 데모에서는 실제 메일은 보내지 않고, 메시지만 로깅합니다.
# 실제로 SendGrid를 사용하려면 아래 주석을 해제하고, 필요한 환경 변수를 설정하세요.
# 예: SENDGRID_API_KEY, SENDER_EMAIL, RECIPIENT_EMAIL
# import sendgrid
# from sendgrid import SendGridAPIClient
# from sendgrid.helpers.mail import Mail, Email, Personalization

logger = logging.getLogger(__name__)

# 중요: func.FunctionApp() 인스턴스는 프로젝트 전체에서 단 한 번만 정의되어야 합니다.
# 이 파일의 최상단에 위치하는 것이 일반적입니다.
app = func.FunctionApp()

# ==============================================================================
# 1. RobotStatusChangeLogger 함수 (Event Grid Trigger)
# 모든 로봇 상태 변경 이벤트를 수신하여 로그를 기록합니다.
# ==============================================================================
@app.event_grid_trigger(arg_name="event")
def RobotStatusChangeLogger(event: func.EventGridEvent):
    logger.info('Python Event Grid trigger processed RobotStatusChangeLogger event.')
    
    try:
        event_data = event.get_json()
        robot_telemetry_body = event_data.get('data', {}).get('body', {})

        if not robot_telemetry_body:
            logger.warning(f"Logger: Event body is empty or malformed: {event_data}")
            return

        device_id = robot_telemetry_body.get('deviceId', 'N/A')
        battery_level = robot_telemetry_body.get('batteryLevel', 'N/A')
        current_status = robot_telemetry_body.get('currentStatus', 'N/A')
        ttimestamp = robot_telemetry_body.get('ttimestamp', 'N/A')

        log_message = (
            f"RobotTelemetryLog - DeviceId: {device_id}, "
            f"Timestamp: {ttimestamp}, "
            f"Battery: {battery_level}%, Status: {current_status}"
        )
        logger.info(log_message)

    except json.JSONDecodeError:
        logger.error(f"Logger: Could not decode JSON from Event Grid event: {event.get_body()}")
    except Exception as e:
        logger.error(f"Logger: Error processing Event Grid event: {e}", exc_info=True)
    